# SPDX-License-Identifier: Apache-2.0
"""Combined diagnostic, observer, Classic and FeliCa synthetic regression."""
import ctypes as c
import unittest
import test_gate as gate
from test_ch559_classic_gate import CandidateReader
from test_ch559_classic_4k_gate import Classic4KGateTests
from test_ch559_felica_gate import FelicaGateTests

class IntegratedGateTests(Classic4KGateTests):
    @classmethod
    def setUpClass(cls):
        class Fixture(gate.GateTests):
            extra_flags=('-DMG_SOFT_B','-DMG_COMPACT_ABI','-DMG_UID_PROFILE','-DMG_EVENTS',
                         '-DMG_CH559','-DMG_CH559_CLASSIC','-DMG_CLASSIC_STACK_AUTO',
                         '-DMG_CH559_FELICA','-DMG_CLASSIC_4K','-DMG_CLASSIC_7B',
                         '-DMG_CCID_DIAGNOSTIC','-DMG_STANDALONE_OBSERVER')
            def setUp(self):
                super().setUp();self.r=CandidateReader.in_dll(self.lib,'reader_state')
        cls.fixture=Fixture;Fixture.setUpClass();cls.addClassCleanup(Fixture.doClassCleanups)

    def test_diagnostic_and_observer_with_active_card(self):
        f=self.fixture();f.setUp();f.lib.mg_standalone_init()
        for payload in (gate.VERSION,b'',b'',b'',b''):f.respond(payload)
        f.lib.mg_standalone_poll()
        f.send(gate.command(0x62));f.respond(b'')
        f.respond(bytes.fromhex('01010004080401020304'));f.final()
        f.lib.mg_standalone_poll()
        self.assertEqual((f.lib.mg_standalone_reader(),f.lib.mg_standalone_card(),f.lib.mg_standalone_host()),(1,1,1))
        self.assertEqual(f.lib.mg_standalone_take(),7)
        f.setup(0xc0,0x5d,length=8)
        self.assertEqual(f.get('UEP0_T_LEN'),8)
        self.assertEqual(bytes(f.ep0[2:4]),bytes([0,0]))

    def test_diagnostic_stack_observation(self):
        f=self.fixture();f.setUp()
        ram=(c.c_uint8*256).in_dll(f.lib,'usb_test_iram')
        ram[:]=bytes([0xa5])*256
        ram[0x8c]=0
        before=bytes(ram)
        f.setup(0xc0,0x5b,length=2)
        self.assertEqual(bytes(f.ep0[:2]),bytes([0x44,0x8c]))
        self.assertEqual(bytes(ram),before)
        f.setup(0xc0,0x5b,length=1)
        self.assertEqual(f.get('UEP0_CTRL'),0x0f)

    def test_normal_candidate_does_not_expose_standalone_diagnostic(self):
        f=self.fixture();f.setUp();f.setup(0xc0,0x5f,length=3)
        self.assertEqual(f.get('UEP0_CTRL'),0x0f)

    def test_invalid_background_card_has_one_bounded_recovery(self):
        f=self.fixture();f.setUp()
        for payload in (gate.VERSION,b'',b'',b'',b''):f.respond(payload)
        f.notifications();f.poll(200)
        self.assertEqual(f.g.background,1)
        f.respond(b'\x01\x01')
        self.assertEqual(f.g.startup_retry,0)
        self.assertNotEqual(f.r.phase,gate.R_FAILED)
        for payload in (gate.VERSION,b'',b'',b'',b''):f.respond(payload)
        f.notifications();f.poll(200)
        self.assertEqual(f.g.background,1)
        f.respond(b'\x01\x01')
        self.assertEqual(f.r.phase,gate.R_FAILED)
        before=f.sent()
        for _ in range(5):f.poll(2000)
        self.assertEqual((f.r.phase,f.sent()),(gate.R_FAILED,before))

    def test_reader_idle_with_busy_transport_reproduces_diagnostic_code(self):
        f=self.fixture();f.setUp()
        for payload in (gate.VERSION,b'',b'',b'',b''):f.respond(payload)
        f.lib.reader_release.argtypes=[c.c_void_p];f.lib.reader_release(c.byref(f.r))
        self.assertEqual(f.r.phase,gate.R_IDLE)
        f.r.pn.phase=2
        before=f.sent();f.lib.reader_scan.argtypes=[c.c_void_p,c.c_uint8,c.c_uint8,c.c_uint16]
        f.lib.reader_scan(c.byref(f.r),0,0,f.now)
        self.assertEqual((f.r.phase,f.r.error,f.r.pn.error),(gate.R_FAILED,32,0))
        self.assertEqual(f.sent(),before)

    def test_invalid_background_card_does_not_recover_with_partial_request(self):
        f=self.fixture();f.setUp()
        for payload in (gate.VERSION,b'',b'',b'',b''):f.respond(payload)
        f.notifications();f.poll(200)
        self.assertEqual(f.g.background,1)
        f.send(gate.command(0x65)[:3])
        self.assertEqual(f.g.header_used,3)
        f.respond(b'\x01\x01')
        self.assertEqual((f.r.phase,f.g.startup_retry),(gate.R_FAILED,1))

    def test_diagnostic_distinguishes_receive_deadline_from_usb_fault(self):
        f=self.fixture();f.setUp()
        for payload in (gate.VERSION,b'',b'',b'',b''):f.respond(payload)
        f.send(b'\x6f\x04\0');f.poll(1100)
        f.setup(0xc0,0x5d,length=8)
        self.assertEqual((f.ep0[2],f.ep0[6],f.ep0[7]),(1,0,0))
        f.lib.test_reset();f.poll();f.setup(0,9,1);f.transfer(0x20,0)
        for payload in (gate.VERSION,b'',b'',b'',b''):f.respond(payload)
        c.c_uint8.in_dll(f.lib,'USB_INT_FG').value=0x10
        f.poll();f.setup(0xc0,0x5d,length=8)
        self.assertEqual((f.ep0[2],f.ep0[7]),(1,1))

    def test_unconsumed_poweron_extension_blocks_queued_request_until_reset(self):
        f=self.fixture();f.setUp()
        for payload in (gate.VERSION,b'',b'',b'',b''):f.respond(payload)
        f.send(gate.command(0x62));f.respond(b'');f.respond(b'\0')
        self.assertEqual(f.g.job,6)
        f.poll(300)
        self.assertEqual((f.g.active,f.g.response,f.get('usb_in_armed')),(1,1,1))
        f.send(gate.command(0x65,sequence=42))
        self.assertEqual(f.get('usb_out_pending'),1)
        f.poll(16000)
        f.setup(0xc0,0x5d,length=8)
        self.assertEqual(bytes(f.ep0[:8]),bytes([6,0,0,1,1,1,1,0]))
        f.lib.test_reset();f.poll()
        self.assertEqual((f.g.active,f.g.response,f.get('usb_out_pending'),
                          f.get('usb_in_armed')),(0,0,0,0))

    def test_stalled_poweron_endpoint_clear_allows_fresh_ccid(self):
        f=self.fixture();f.setUp()
        for payload in (gate.VERSION,b'',b'',b'',b''):f.respond(payload)
        f.send(gate.command(0x62));f.respond(b'');f.respond(b'\0')
        f.poll(300);f.send(gate.command(0x65,sequence=42));f.poll(16000)
        f.setup(0xc0,0x5d,length=8)
        self.assertEqual(bytes(f.ep0[:8]),bytes([6,0,0,1,1,1,1,0]))
        f.setup(0x02,1,index=2);f.poll()
        self.assertEqual((f.g.active,f.g.response,f.get('usb_out_pending'),
                          f.get('usb_in_armed')),(0,0,0,0))
        f.send(gate.command(0x65,sequence=43));reply,_=f.final()
        self.assertEqual((reply[0],reply[6],reply[7]&0xc0),(0x81,43,0))

    def test_delayed_host_consumes_extension_then_deadline_and_queued_status(self):
        f=self.fixture();f.setUp()
        for payload in (gate.VERSION,b'',b'',b'',b''):f.respond(payload)
        f.send(gate.command(0x62,sequence=41));f.respond(b'');f.respond(b'\0')
        f.poll(300)
        f.send(gate.command(0x65,sequence=42));f.poll(16000)
        extension,_=f.collect()
        self.assertEqual((extension[6],extension[7]&0xc0),(41,0x80))
        failure,_=f.collect()
        self.assertEqual((failure[6],failure[7]&0xc0),(41,0x40))
        status,_=f.collect()
        self.assertEqual((status[0],status[6],status[7]&0xc0),(0x81,42,0))

class IntegratedFelicaRegression(FelicaGateTests):
    @classmethod
    def setUpClass(cls):
        class Fixture(gate.GateTests):
            extra_flags=('-DMG_SOFT_B','-DMG_COMPACT_ABI','-DMG_UID_PROFILE','-DMG_EVENTS',
                         '-DMG_CH559','-DMG_CH559_CLASSIC','-DMG_CLASSIC_STACK_AUTO',
                         '-DMG_CH559_FELICA','-DMG_CLASSIC_4K','-DMG_CLASSIC_7B',
                         '-DMG_CCID_DIAGNOSTIC','-DMG_STANDALONE_OBSERVER')
            def setUp(self):
                super().setUp();self.r=CandidateReader.in_dll(self.lib,'reader_state')
        cls.fixture=Fixture;Fixture.setUpClass();cls.addClassCleanup(Fixture.doClassCleanups)
