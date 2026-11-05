# SPDX-License-Identifier: Apache-2.0
"""USB-unconfigured background discovery in an isolated CH559 profile."""
import ctypes as c
import unittest
import test_gate as gate
from test_ch559_classic_gate import CandidateReader
from test_pn532_frame import response
from test_card import type_b
from test_standalone_observer import Snapshot


class StandaloneScanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        class Fixture(gate.GateTests):
            extra_flags=('-DMG_SOFT_B','-DMG_COMPACT_ABI','-DMG_UID_PROFILE','-DMG_EVENTS',
                         '-DMG_CH559','-DMG_CH559_CLASSIC','-DMG_CLASSIC_STACK_AUTO',
                         '-DMG_CH559_FELICA','-DMG_CLASSIC_4K','-DMG_CLASSIC_7B',
                         '-DMG_STANDALONE_OBSERVER','-DMG_STANDALONE_SCAN','-DMG_CCID_DIAGNOSTIC','-DMG_RESET_DIAGNOSTIC',
                         '-DMG_DISPATCH_CONSUMER_1=dispatch_probe_1',
                         '-DMG_DISPATCH_CONSUMER_2=dispatch_probe_2')
            def setUp(self):
                super().setUp();self.r=CandidateReader.in_dll(self.lib,'reader_state')
        cls.fixture=Fixture;Fixture.setUpClass();cls.addClassCleanup(Fixture.doClassCleanups)

    def test_reset_diagnostic_exposes_only_two_flag_bits(self):
        f=self.fixture();f.setUp()
        for value in range(256):
            c.c_uint8.in_dll(f.lib,'PCON').value=value;f.setup(0xc0,0x60,length=1)
            self.assertEqual((f.get('UEP0_T_LEN'),f.ep0[0]),(1,(value>>4)&3))
        for length in (0,2):
            f.setup(0xc0,0x60,length=length);self.assertEqual(f.get('UEP0_CTRL'),0x0f)
        for value,index in ((1,0),(0x100,0),(0,1),(0,0x100)):
            f.setup(0xc0,0x60,value=value,index=index,length=3)
            self.assertEqual(f.get('UEP0_CTRL'),0x0f)
        c.c_uint16.in_dll(f.lib,'milliseconds').value=0x9abc
        c.c_uint8.in_dll(f.lib,'EA').value=1
        f.setup(0xc0,0x60,length=3)
        self.assertEqual(bytes(f.ep0[:3]),bytes([3,0xbc,0x9a]))
        self.assertEqual(f.get('EA'),1)

    def test_selected_family_diagnostic_requires_selection(self):
        f=self.fixture();f.setUp()
        for family in (0,1,2,3):
            f.r.card.type=family
            f.r.selected=0;f.setup(0xc0,0x5e,length=1)
            self.assertEqual((f.get('UEP0_T_LEN'),f.ep0[0]),(1,0xff))
            f.r.selected=1;f.setup(0xc0,0x5e,length=1)
            self.assertEqual(f.ep0[0],family)
        f.setup(0xc0,0x5e,length=2);self.assertEqual(f.get('UEP0_CTRL'),0x0f)

    def test_cold_start_without_usb_configuration(self):
        f=self.fixture();f.setUp();lib=f.lib
        lib.uart_init();lib.test_usb_init();lib.gate_init(0);lib.mg_standalone_init()
        f.now=0
        self.assertEqual(f.get('usb_configured'),0)
        f.setup(0xc0,0x5f,length=3)
        self.assertEqual((f.get('UEP0_T_LEN'),f.ep0[1],f.ep0[2]),(3,0,0))
        for payload in (gate.VERSION,b'',b'',b'',b''):f.respond(payload)
        f.poll(200);self.assertEqual(f.g.background,1)
        f.respond(bytes.fromhex('01010004080401020304'));lib.mg_standalone_poll()
        self.assertEqual((f.r.present,lib.mg_standalone_card(),lib.mg_standalone_host()),(1,1,0))
        f.setup(0xc0,0x5f,length=3)
        self.assertEqual((f.get('UEP0_T_LEN'),f.ep0[1],f.ep0[2]),(3,1,0))
        f.setup(0xc0,0x5f,length=4)
        self.assertEqual(f.get('UEP0_CTRL'),0x0f)

    def test_offline_scan_and_removal_then_usb_configuration(self):
        f=self.fixture();f.setUp();f.lib.mg_standalone_init()
        f.setup(0,9,0);f.transfer(0x20,0)
        self.assertEqual(f.get('usb_configured'),0)
        for payload in (gate.VERSION,b'',b'',b'',b''):f.respond(payload)
        f.poll(200);self.assertEqual(f.g.background,1)
        f.respond(bytes.fromhex('01010004080401020304'))
        f.lib.mg_standalone_poll()
        self.assertEqual((f.r.present,f.lib.mg_standalone_card(),f.lib.mg_standalone_host()),(1,1,0))
        f.poll(200);self.assertEqual(f.g.background,2)
        f.respond(b'\x01');f.lib.mg_standalone_poll()
        self.assertEqual((f.r.present,f.lib.mg_standalone_card()),(0,0))
        f.setup(0,9,1);f.transfer(0x20,0)
        self.assertEqual(f.get('usb_configured'),1)
        for payload in (gate.VERSION,b'',b'',b'',b''):f.respond(payload)
        f.send(gate.command(0x65,sequence=42));reply,_=f.final()
        self.assertEqual((reply[0],reply[6],reply[7]&0xc0),(0x81,42,0))

    def test_offline_scan_reaches_type_f_without_exposing_uid(self):
        f=self.fixture();f.setUp();f.lib.mg_standalone_init()
        f.setup(0,9,0);f.transfer(0x20,0)
        for payload in (gate.VERSION,b'',b'',b'',b''):f.respond(payload)
        f.poll(200);f.respond(b'\0');f.respond(b'\0')
        f.respond(bytes([1,1,18,1])+bytes(range(1,9))+bytes(range(0x20,0x28)))
        f.lib.mg_standalone_poll()
        self.assertEqual((f.r.present,f.r.card.type,f.lib.mg_standalone_card()),(1,2,1))
        self.assertEqual(f.get('usb_configured'),0)

    def test_offline_scan_reaches_type_b(self):
        f=self.fixture();f.setUp();f.lib.mg_standalone_init()
        f.setup(0,9,0);f.transfer(0x20,0)
        for payload in (gate.VERSION,b'',b'',b'',b''):f.respond(payload)
        f.poll(200);f.respond(b'\0');f.respond(type_b())
        f.lib.mg_standalone_poll()
        self.assertEqual((f.r.present,f.r.card.type,f.lib.mg_standalone_card()),(1,3,1))
        self.assertEqual(f.get('usb_configured'),0)

    def test_usb_configuration_discards_inflight_offline_scan(self):
        f=self.fixture();f.setUp();f.lib.mg_standalone_init()
        f.setup(0,9,0);f.transfer(0x20,0)
        for payload in (gate.VERSION,b'',b'',b'',b''):f.respond(payload)
        f.poll(200);self.assertEqual((f.g.background,f.r.pn.command),(1,0x4a))
        f.setup(0,9,1);f.transfer(0x20,0)
        self.assertEqual((f.get('usb_configured'),f.g.background,f.r.present),(1,0,0))
        for byte in gate.ACK+response(bytes.fromhex('01010004080401020304'),command=0x4b):
            f.lib.test_feed(byte)
        for _ in range(20):f.poll()
        self.assertEqual(f.r.present,0)
        for payload in (gate.VERSION,b'',b'',b'',b''):f.respond(payload)
        f.send(gate.command(0x65,sequence=43));reply,_=f.final()
        self.assertEqual((reply[0],reply[6],reply[7]&0xc0),(0x81,43,0))
        self.assertEqual(reply[7]&3,2)

    def test_usb_reset_invalidates_old_session_then_scans_offline(self):
        f=self.fixture();f.setUp();f.lib.mg_standalone_init()
        for payload in (gate.VERSION,b'',b'',b'',b''):f.respond(payload)
        f.power_on();self.assertEqual((f.r.active,f.g.powered),(1,1))
        f.lib.test_reset();f.poll();f.lib.mg_standalone_poll()
        self.assertEqual((f.get('usb_configured'),f.r.active,f.g.powered), (0,0,0))
        self.assertEqual((f.lib.mg_standalone_card(),f.lib.mg_standalone_host()),(0,0))
        for payload in (gate.VERSION,b'',b'',b'',b''):f.respond(payload)
        f.poll(200);self.assertEqual(f.g.background,1)
        f.respond(bytes.fromhex('01010004080401020304'));f.lib.mg_standalone_poll()
        self.assertEqual((f.r.present,f.r.active,f.g.powered,f.lib.mg_standalone_card()),(1,0,0,1))

    def test_offline_card_changes_reach_both_consumers(self):
        f=self.fixture();f.setUp();lib=f.lib
        for name in ('dispatch_calls_1','dispatch_calls_2'):c.c_uint.in_dll(lib,name).value=0
        lib.mg_standalone_init();f.setup(0,9,0);f.transfer(0x20,0)
        for payload in (gate.VERSION,b'',b'',b'',b''):f.respond(payload)
        lib.mg_standalone_poll();lib.mg_dispatch_poll()
        f.poll(200);f.respond(bytes.fromhex('01010004080401020304'))
        lib.mg_standalone_poll();lib.mg_dispatch_poll()
        a=Snapshot.in_dll(lib,'dispatch_seen_1');b=Snapshot.in_dll(lib,'dispatch_seen_2')
        self.assertEqual((a.state.card_present,a.state.host_connected,a.changes & 2,a.events & 2),(1,0,2,2))
        self.assertEqual((b.state.card_present,b.state.host_connected,b.changes,b.events),
                         (a.state.card_present,a.state.host_connected,a.changes,a.events))
        f.poll(200);f.respond(b'\x01');lib.mg_standalone_poll();lib.mg_dispatch_poll()
        self.assertEqual((a.state.card_present,a.state.host_connected,a.changes & 2,a.events & 4),(0,0,2,4))
        self.assertEqual((b.state.card_present,b.state.host_connected,b.changes,b.events),
                         (a.state.card_present,a.state.host_connected,a.changes,a.events))

    def test_malformed_offline_discovery_has_one_bounded_recovery(self):
        f=self.fixture();f.setUp();f.setup(0,9,0);f.transfer(0x20,0)
        for payload in (gate.VERSION,b'',b'',b'',b''):f.respond(payload)
        f.poll(200);f.respond(b'\x01\x01')
        self.assertEqual(f.g.startup_retry,0)
        self.assertNotEqual(f.r.phase,gate.R_FAILED)
        for payload in (gate.VERSION,b'',b'',b'',b''):f.respond(payload)
        f.poll(200);f.respond(b'\x01\x01')
        self.assertEqual(f.r.phase,gate.R_FAILED)
        before=f.sent()
        for _ in range(5):f.poll(2000)
        self.assertEqual((f.r.phase,f.sent()),(gate.R_FAILED,before))

    def test_successful_card_detection_renews_bounded_recovery(self):
        f=self.fixture();f.setUp();f.setup(0,9,0);f.transfer(0x20,0)
        for payload in (gate.VERSION,b'',b'',b'',b''):f.respond(payload)
        f.poll(200);f.respond(b'\x01\x01')
        self.assertEqual(f.g.startup_retry,0)
        for payload in (gate.VERSION,b'',b'',b'',b''):f.respond(payload)
        f.poll(200);f.respond(bytes.fromhex('01010004080401020304'))
        self.assertEqual((f.r.present,f.g.startup_retry),(1,1))
        f.poll(200);f.respond(b'\x01')
        f.poll(200);f.respond(b'\x01\x01')
        self.assertEqual(f.g.startup_retry,0)
        self.assertNotEqual(f.r.phase,gate.R_FAILED)
        for payload in (gate.VERSION,b'',b'',b'',b''):f.respond(payload)
        f.poll(200);f.respond(b'\x01\x01')
        self.assertEqual(f.r.phase,gate.R_FAILED)

    def test_offline_discovery_timeout_stays_failed_until_usb_reset(self):
        f=self.fixture();f.setUp();f.setup(0,9,0);f.transfer(0x20,0)
        for payload in (gate.VERSION,b'',b'',b'',b''):f.respond(payload)
        f.poll(200);self.assertEqual(f.g.background,1)
        f.r.pn.phase=gate.FAILED;f.r.pn.error=33;f.poll()
        self.assertEqual((f.r.phase,f.r.error,f.g.background),(gate.R_FAILED,33,0))
        before=f.sent()
        for _ in range(5):f.poll(2000)
        self.assertEqual((f.r.phase,f.sent()),(gate.R_FAILED,before))
        f.lib.test_reset();f.poll()
        self.assertNotEqual(f.r.phase,gate.R_FAILED)
