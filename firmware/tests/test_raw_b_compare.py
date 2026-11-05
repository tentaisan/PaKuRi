# SPDX-License-Identifier: Apache-2.0
import ctypes as c
import unittest
import test_reader as reader
from test_pn532_frame import array, response

REQUEST=bytes.fromhex('00a4040070')+bytes(113)


class RawComparisonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture=type('RawFixture',(reader.ReaderTests,),{'singleton':True,'extra_flags':getattr(cls,'flags',('-DMG_RAW_B_COMPARE',))})
        cls.fixture.setUpClass();cls.addClassCleanup(cls.fixture.doClassCleanups)

    def prepare(self):
        fx=self.fixture();fx.setUp();fx.initialize();fx.scan(3);fx.lib.reader_release(c.byref(fx.r));return fx

    def test_only_fixed_request_becomes_first_type_b_i_block(self):
        fx=self.prepare();before=len(fx.sent())
        self.assertEqual(fx.exchange(REQUEST),0)
        fx.respond(b'\0\x0a\x01\x67\0')
        self.assertEqual(fx.sent()[before:],response(b'\x0a\x01'+REQUEST,0xd4,0x42))
        self.assertEqual(fx.r.phase,reader.R_DONE)
        self.assertEqual(fx.r.pn.payload,2)
        self.assertEqual(bytes(fx.r.pn.frame[fx.r.pn.offset:fx.r.pn.offset+2]),b'\x67\0')
        fx.lib.reader_release(c.byref(fx.r));before=fx.sent()
        self.assertEqual(fx.exchange(REQUEST),3)
        self.assertEqual(fx.sent(),before)

    def test_every_request_byte_and_family_cid_length_are_guarded(self):
        fx=self.prepare();before=fx.sent()
        for i in range(len(REQUEST)):
            altered=bytearray(REQUEST);altered[i]^=1
            self.assertEqual(fx.exchange(bytes(altered)),3)
        for request in (REQUEST[:-1],REQUEST+b'\0',b'\0\xb0\0\0\0'):
            self.assertEqual(fx.exchange(request),3)
        fx.r.card.type=0;self.assertEqual(fx.exchange(REQUEST),3)
        fx.r.card.type=3;fx.r.card.cid=0;self.assertEqual(fx.exchange(REQUEST),3)
        self.assertEqual(fx.sent(),before)

    def test_invalid_raw_reply_and_pn_status_fail_closed(self):


        for payload in (b'\x01',b'\x10',b'\0\xfa\x01\x02',
                        b'\0\x0b\x01\x67\0',b'\0\x0a\x02\x67\0',
                        b'\0\x0a\x01\x67',b'\0\x0a\x01\x67\0\0'):
            fx=self.prepare();self.assertEqual(fx.exchange(REQUEST),0);fx.respond(payload)
            self.assertEqual(fx.r.phase,reader.R_FAILED)
            self.assertFalse(fx.r.active);self.assertFalse(fx.r.selected)
            self.assertEqual(fx.r.rf_status,payload[0])


class RawControlTests(RawComparisonTests):
    flags=('-DMG_RAW_B_COMPARE','-DMG_RAW_B_CONTROL')

    def test_short_control_is_exact_and_one_shot_requires_fresh_activation(self):
        request=bytes.fromhex('00a4040010')+bytes(17)
        fx=self.prepare();before=fx.sent()
        for i in range(len(request)):
            altered=bytearray(request);altered[i]^=1
            self.assertEqual(fx.exchange(bytes(altered)),3)
        for length in range(4,119):
            if length in (22,118):continue
            rejected=bytes((0,0xa4,4,0,max(0,length-6)))+bytes(max(0,length-5))
            self.assertEqual(fx.exchange(rejected),3)
        self.assertEqual(fx.sent(),before)

        self.assertEqual(fx.exchange(request),0);fx.respond(b'\0\x0a\x01\x6a\x82')
        self.assertEqual(fx.sent()[len(before):],response(b'\x0a\x01'+request,0xd4,0x42))
        fx.lib.reader_release(c.byref(fx.r));before=fx.sent()
        self.assertEqual(fx.exchange(REQUEST),3)
        self.assertEqual(fx.sent(),before)


class RawTimedTests(RawControlTests):
    flags=('-DMG_RAW_B_COMPARE','-DMG_RAW_B_CONTROL','-DMG_RAW_B_TIMED')

    def prepare(self):
        fx=self.fixture();fx.setUp()
        for payload in (reader.VERSION,b'',b'',b'',b''):fx.respond(payload)
        self.assertEqual((fx.r.phase,fx.r.initialized),(reader.R_DONE,1))
        fx.lib.reader_release(c.byref(fx.r))
        payload=bytearray(reader.type_b());payload[13]=0xa1
        fx.scan(3,payload=bytes(payload));fx.lib.reader_release(c.byref(fx.r));return fx

    def test_finite_rf_timing_is_added_without_removing_activation_retry_limit(self):
        fx=self.prepare();wire=fx.sent()
        timing=response(bytes.fromhex('02000b0d'),0xd4,0x32)
        retries=response(bytes.fromhex('05000000'),0xd4,0x32)
        self.assertEqual(wire.count(timing),1);self.assertEqual(wire.count(retries),1)
        self.assertLess(wire.index(timing),wire.index(retries))

        fx=self.fixture();fx.setUp()
        for payload in (reader.VERSION,b'',b''):fx.respond(payload)
        self.assertEqual(fx.r.phase,13)
        fx.respond(b'\0')
        self.assertEqual((fx.r.phase,fx.r.initialized),(reader.R_FAILED,0))

    def test_diagnostic_rejects_type_a_instead_of_using_an_unchecked_parser(self):
        fx=self.prepare()
        fx.lib.reader_field_off(c.byref(fx.r),fx.now);fx.respond(b'')
        fx.lib.reader_release(c.byref(fx.r));fx.scan(0)
        self.assertFalse(fx.r.present);self.assertFalse(fx.r.active)

    def test_fwi_and_fsci_are_checked_in_firmware_before_any_rf_transmission(self):
        for index,value in ((9,0x71),(10,0x91),(10,0xb1)):
            fx=self.prepare();before=fx.sent();fx.r.card.atr[index]=value
            self.assertEqual(fx.exchange(REQUEST),3);self.assertEqual(fx.sent(),before)
