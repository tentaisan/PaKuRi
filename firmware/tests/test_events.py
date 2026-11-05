# SPDX-License-Identifier: Apache-2.0
"""Synthetic gate events with no output device and no card data in events."""
import ctypes as c
import unittest
import test_gate as gate
from test_uid_profile import UidReader

READY, PRESENT, ABSENT, START, DONE, FAILED, READER_FAILED, RESET = (1,2,4,8,16,32,64,128)
CANCELLED = 256
USB_FAULT = 512


class EventGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        class Fixture(gate.GateTests):
            extra_flags = ('-DMG_SOFT_B', '-DMG_COMPACT_ABI', '-DMG_UID_PROFILE', '-DMG_EVENTS')
            def setUp(self):
                super().setUp(); self.r = UidReader.in_dll(self.lib, 'reader_state')
        cls.fixture = Fixture; Fixture.setUpClass(); cls.addClassCleanup(Fixture.doClassCleanups)
        Fixture.lib.mg_events_take.restype = c.c_uint16

    def setUp(self):
        self.f = self.fixture(); self.f.setUp()

    def events(self): return self.f.lib.mg_events_take()

    def power(self):
        f = self.f
        for payload in (gate.VERSION, b'', b'', b'', b''): f.respond(payload)
        self.assertTrue(self.events() & READY)
        f.send(gate.command(0x62)); f.respond(b'')
        f.respond(bytes.fromhex('01010004080411223344')); f.final()
        self.assertTrue(self.events() & PRESENT)

    def test_card_and_exchange_events_are_edges_and_coalesce(self):
        self.power(); f = self.f
        f.send(gate.command(0x6f, bytes.fromhex('ffca000000'))); f.final()
        self.assertEqual(self.events(), START | DONE)
        self.assertEqual(self.events(), 0)
        f.notifications(); f.poll(200); f.respond(b'\x00'); f.respond(b'\x01')
        self.assertTrue(self.events() & ABSENT)
        self.assertEqual(self.events(), 0)

    def test_failed_exchange_and_reset_events(self):
        self.power(); f = self.f
        f.send(gate.command(0x6f, bytes.fromhex('ffb0000010'))); f.final()
        self.assertEqual(self.events(), START | FAILED)
        f.lib.test_reset(); f.poll()
        flags = self.events()
        self.assertTrue(flags & RESET)
        self.assertTrue(flags & ABSENT)

    def test_pending_flags_are_reset_on_initialization(self):
        self.power()
        self.f.lib.gate_init(0)
        self.assertEqual(self.events(), 0)

    def test_usb_fault_is_reported_once_and_closes_receive(self):
        f = self.f
        self.events()
        c.c_uint8.in_dll(f.lib, 'usb_events').value = 16
        f.poll()
        self.assertTrue(self.events() & USB_FAULT)
        self.assertEqual(f.g.rx_closed, 1)
        f.poll()
        self.assertFalse(self.events() & USB_FAULT)

    def test_usb_fault_cancels_inflight_exchange_without_replay(self):
        f = self.f
        for payload in (gate.VERSION, b'', b'', b'', b''): f.respond(payload)
        f.power_on(0); self.events()
        f.send(gate.command(0x6f, bytes.fromhex('00a4040000')))
        self.assertTrue(self.events() & START)
        for _ in range(1000):
            if f.r.pn.phase == gate.ACK_WAIT: break
            f.poll()
        else:
            self.fail('PN532 request did not reach ACK wait')
        before = f.sent()
        self.assertEqual(before.count(bytes.fromhex('d44001')), 1)
        c.c_uint8.in_dll(f.lib, 'USB_INT_FG').value = 0x10
        f.poll()
        flags = self.events()
        self.assertEqual(flags & (USB_FAULT | CANCELLED), USB_FAULT | CANCELLED)
        self.assertFalse(flags & DONE)
        self.assertEqual((f.g.active, f.g.response, f.g.rx_closed), (0, 0, 1))
        f.poll()

        self.assertEqual(f.sent().count(bytes.fromhex('d44001')),
                         before.count(bytes.fromhex('d44001')))

    def test_reader_failure_is_an_edge_not_a_repeated_notification(self):
        self.power(); f = self.f
        f.r.pn.phase = 7; f.r.pn.error = 34; f.poll()
        self.assertTrue(self.events() & READER_FAILED)
        f.poll(); self.assertFalse(self.events() & READER_FAILED)

    def test_start_failure_publishes_immediately(self):
        f = self.f
        for payload in (gate.VERSION, b'', b'', b'', b''): f.respond(payload)
        self.events()
        f.r.phase = 6; f.r.active = 0
        f.r.pn.phase = 2
        f.lib.mg_reader_scan.argtypes = (c.c_uint8, c.c_uint8, c.c_uint16)
        f.lib.mg_reader_scan(0, 0, f.now)
        self.assertTrue(self.events() & READER_FAILED)
        f.poll()
        self.assertFalse(self.events() & READER_FAILED)

    def test_reset_cancels_an_inflight_exchange(self):
        f = self.f
        for payload in (gate.VERSION, b'', b'', b'', b''): f.respond(payload)
        f.power_on(0); self.events()
        f.send(gate.command(0x6f, bytes.fromhex('00a4040000')))
        self.assertTrue(self.events() & START)
        f.lib.test_reset(); f.poll()
        flags = self.events()
        self.assertEqual(flags & (RESET | CANCELLED), RESET | CANCELLED)
        self.assertFalse(flags & DONE)
