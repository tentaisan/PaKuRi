# SPDX-License-Identifier: Apache-2.0
"""Synthetic live reader and USB snapshots without a physical output device."""
import ctypes as c
import unittest
import test_gate as gate
from test_standalone_state import State
from test_uid_profile import UidReader

class Snapshot(c.Structure):
    _fields_=[('state',State),('changes',c.c_uint8),('events',c.c_uint16)]

class StandaloneObserverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        class Fixture(gate.GateTests):
            extra_flags=('-DMG_SOFT_B','-DMG_COMPACT_ABI','-DMG_UID_PROFILE','-DMG_EVENTS',
                         '-DMG_STANDALONE_OBSERVER','-DMG_DISPATCH_CONSUMER_1=dispatch_probe_1',
                         '-DMG_DISPATCH_CONSUMER_2=dispatch_probe_2')
            def setUp(self):
                super().setUp();self.r=UidReader.in_dll(self.lib,'reader_state')
        cls.fixture=Fixture;Fixture.setUpClass();cls.addClassCleanup(Fixture.doClassCleanups)
        cls.fixture.lib.mg_standalone_observe.argtypes=[c.POINTER(State)]
        cls.fixture.lib.mg_standalone_observe.restype=c.c_uint8
        cls.fixture.lib.mg_events_take.restype=c.c_uint16

    def test_observer_tracks_live_state_without_consuming_events(self):
        f=self.fixture();f.setUp();state=State(0,0,0)
        observe=lambda: f.lib.mg_standalone_observe(c.byref(state))
        self.assertEqual(observe(),4)
        for payload in (gate.VERSION,b'',b'',b'',b''):f.respond(payload)
        self.assertEqual(observe(),1);self.assertEqual(state.reader,1)
        f.send(gate.command(0x62));f.respond(b'')
        f.respond(bytes.fromhex('01010004080401020304'));f.final()
        self.assertEqual(observe(),2);self.assertEqual(state.card_present,1)
        self.assertTrue(f.lib.mg_events_take() & 2)
        f.r.pn.phase=7;f.r.pn.error=34;f.poll()
        self.assertEqual(observe(),3);self.assertEqual((state.reader,state.card_present),(2,0))
        f.setup(0,9,0);f.transfer(0x20,0)
        self.assertEqual(observe() & 4,4);self.assertEqual(state.host_connected,0)

    def test_dispatch_fans_out_observer_and_gate_flags(self):
        f=self.fixture();f.setUp();lib=f.lib
        for name in ('dispatch_calls_1','dispatch_calls_2'):c.c_uint.in_dll(lib,name).value=0
        lib.mg_standalone_init();lib.mg_standalone_poll();lib.mg_dispatch_poll()
        for payload in (gate.VERSION,b'',b'',b'',b''):f.respond(payload)
        f.send(gate.command(0x62));f.respond(b'')
        f.respond(bytes.fromhex('01010004080401020304'));f.final()
        lib.mg_standalone_poll();lib.mg_dispatch_poll()
        a=Snapshot.in_dll(lib,'dispatch_seen_1');b=Snapshot.in_dll(lib,'dispatch_seen_2')
        self.assertEqual((a.state.reader,a.state.card_present,a.state.host_connected,a.changes),(1,1,1,3))
        self.assertEqual((b.state.reader,b.state.card_present,b.state.host_connected,b.changes,b.events),
                         (a.state.reader,a.state.card_present,a.state.host_connected,a.changes,a.events))
        self.assertTrue(a.events & 2)
        self.assertEqual(c.c_uint.in_dll(lib,'dispatch_calls_1').value,2)
        self.assertEqual(c.c_uint.in_dll(lib,'dispatch_calls_2').value,2)
        self.assertEqual((lib.mg_standalone_take(),lib.mg_events_take()),(0,0))

    def test_immediate_start_failure_reaches_both_consumers(self):
        f=self.fixture();f.setUp();lib=f.lib
        lib.mg_standalone_init()
        for payload in (gate.VERSION,b'',b'',b'',b''):f.respond(payload)
        lib.mg_standalone_poll();lib.mg_dispatch_poll()
        for name in ('dispatch_calls_1','dispatch_calls_2'):c.c_uint.in_dll(lib,name).value=0
        f.r.phase=6;f.r.active=0;f.r.pn.phase=2
        lib.mg_reader_scan.argtypes=(c.c_uint8,c.c_uint8,c.c_uint16)
        lib.mg_reader_scan(0,0,f.now)
        lib.mg_standalone_poll();lib.mg_dispatch_poll()
        a=Snapshot.in_dll(lib,'dispatch_seen_1');b=Snapshot.in_dll(lib,'dispatch_seen_2')
        self.assertEqual((a.state.reader,b.state.reader),(2,2))
        self.assertEqual((a.events & 64,b.events & 64),(64,64))
        self.assertEqual((c.c_uint.in_dll(lib,'dispatch_calls_1').value,
                          c.c_uint.in_dll(lib,'dispatch_calls_2').value),(1,1))
        lib.mg_standalone_poll();lib.mg_dispatch_poll()
        self.assertEqual(c.c_uint.in_dll(lib,'dispatch_calls_1').value,1)

    def test_usb_fault_reaches_both_consumers(self):
        f=self.fixture();f.setUp();lib=f.lib
        lib.mg_standalone_init();lib.mg_standalone_poll();lib.mg_dispatch_poll()
        c.c_uint8.in_dll(lib,'usb_events').value=16
        f.poll();lib.mg_standalone_poll();lib.mg_dispatch_poll()
        a=Snapshot.in_dll(lib,'dispatch_seen_1');b=Snapshot.in_dll(lib,'dispatch_seen_2')
        self.assertEqual((a.events & 512,b.events & 512),(512,512))

    def test_retained_state_coalesces_without_consuming_existing_events(self):
        f=self.fixture();f.setUp();lib=f.lib
        lib.mg_standalone_init();lib.mg_standalone_poll()
        self.assertEqual(lib.mg_standalone_take(),4)
        for payload in (gate.VERSION,b'',b'',b'',b''):f.respond(payload)
        lib.mg_standalone_poll()
        f.send(gate.command(0x62));f.respond(b'')
        f.respond(bytes.fromhex('01010004080401020304'));f.final()
        lib.mg_standalone_poll();lib.mg_standalone_poll()
        self.assertEqual((lib.mg_standalone_reader(),lib.mg_standalone_card(),lib.mg_standalone_host()),(1,1,1))
        self.assertEqual(lib.mg_standalone_take(),3)
        self.assertEqual(lib.mg_standalone_take(),0)
        self.assertTrue(lib.mg_events_take() & 2)
