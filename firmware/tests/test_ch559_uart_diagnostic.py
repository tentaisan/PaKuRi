# SPDX-License-Identifier: Apache-2.0
"""Opt-in CH559 UART diagnostic: fixed metadata only, no hardware claim."""
import ctypes as c
import unittest
import test_gate as gate


class UartDiagnosticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        class Fixture(gate.GateTests):
            extra_flags = ('-DMG_SOFT_B', '-DMG_COMPACT_ABI', '-DMG_UID_PROFILE',
                           '-DMG_EVENTS', '-DMG_CH559', '-DMG_CCID_DIAGNOSTIC',
                           '-DMG_UART_DIAGNOSTIC')
        cls.fixture = Fixture
        Fixture.setUpClass()
        cls.addClassCleanup(Fixture.doClassCleanups)

    def test_fixed_read_only_metadata_and_request_validation(self):
        f = self.fixture(); f.setUp()
        diagnostic = c.c_uint8.in_dll(f.lib, 'pn_uart_diagnostic')
        diagnostic.value = 0x32
        f.setup(0xc0, 0x61, length=1)
        self.assertEqual((f.get('UEP0_T_LEN'), f.ep0[0], diagnostic.value), (1, 0x32, 0x32))
        for args in ((0x40, 0x61, 0, 0, 1), (0xc1, 0x61, 0, 0, 1),
                     (0xc0, 0x61, 1, 0, 1), (0xc0, 0x61, 0, 1, 1),
                     (0xc0, 0x61, 0, 0, 0), (0xc0, 0x61, 0, 0, 2)):
            f.setup(*args)
            self.assertEqual(f.get('UEP0_CTRL'), 0x0f)
            self.assertEqual(diagnostic.value, 0x32)

    def test_usb_reset_recovery_preserves_diagnostic_until_transport_init(self):
        f = self.fixture(); f.setUp()
        diagnostic = c.c_uint8.in_dll(f.lib, 'pn_uart_diagnostic')
        diagnostic.value = 0x31
        c.c_uint8.in_dll(f.lib, 'usb_events').value = 1
        f.lib.gate_poll(1)
        f.setup(0xc0, 0x61, length=1)
        self.assertEqual((f.get('UEP0_T_LEN'), f.ep0[0]), (1, 0x31))

        f.lib.gate_init(2)
        self.assertEqual(diagnostic.value, 0)
