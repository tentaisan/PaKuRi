# SPDX-License-Identifier: Apache-2.0
"""Synthetic CCID -> Classic -> PN532 integration; no hardware or real cards."""
import ctypes as c
import unittest
import test_gate as gate
from test_pn532_transport import State
from test_classic_bridge import Card as ClassicSession
from test_ch559_classic_card import Card as CandidateCard
from test_card import type_a, type_b


class CandidateReader(c.Structure):
    _fields_=[('pn',State),('card',CandidateCard)]+[(name,c.c_uint8) for name in
        ('phase','present','active','selected','initialized','error','scan_type','activate','rf_status')]


class ClassicGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        class Fixture(gate.GateTests):
            extra_flags=('-DMG_SOFT_B','-DMG_COMPACT_ABI','-DMG_UID_PROFILE',
                         '-DMG_CH559','-DMG_CH559_CLASSIC','-DMG_CLASSIC_STACK_AUTO')
            def setUp(self):
                super().setUp(); self.r=CandidateReader.in_dll(self.lib,'reader_state')
        cls.fixture=Fixture; Fixture.setUpClass(); cls.addClassCleanup(Fixture.doClassCleanups)

    def ready(self,sak=8):
        f=self.fixture();f.setUp()
        for payload in (gate.VERSION,b'',b'',b'',b''):f.respond(payload)
        f.send(gate.command(0x62));f.respond(b'')
        f.respond(bytes([1,1,0,4,sak,4,1,2,3,4]))
        message,_=f.final()
        self.assertEqual(message[7]&0xc0,0)
        f.notifications()
        return f

    def load(self,f):
        before=f.sent()
        f.send(gate.command(0x6f,bytes.fromhex('ff82000006010203040506')))
        message,_=f.final()
        self.assertEqual(message[10:],bytes.fromhex('9000'))
        self.assertEqual(f.sent(),before)
        self.assertNotIn(bytes.fromhex('010203040506'),bytes(f.r.pn.frame))
        self.assertNotIn(bytes.fromhex('010203040506'),bytes(f.ep2[:64]))

    def exchange(self,f,apdu,response):
        f.send(gate.command(0x6f,apdu));f.respond(response)
        return f.final()[0][10:]

    def test_pcsc_auth_read_write_and_inactivity(self):
        f=self.ready();self.assertEqual(f.r.card.classic_candidate,1);self.load(f)
        before=f.sent();f.poll(5000)
        self.assertEqual(f.sent(),before)
        self.assertEqual(self.exchange(f,bytes.fromhex('ff860000050100046000'),b'\0'),bytes.fromhex('9000'))
        self.assertEqual(self.exchange(f,bytes.fromhex('ffb0000410'),b'\0'+bytes(range(16))),
                         bytes(range(16))+bytes.fromhex('9000'))
        write=bytes.fromhex('ffd6000410')+bytes(range(16))
        self.assertEqual(self.exchange(f,write,b'\0'),bytes.fromhex('9000'))
        before=f.sent();f.send(gate.command(0x6f,bytes.fromhex('ffd6000710')+bytes(16)))
        self.assertEqual(f.final()[0][10:],bytes.fromhex('6986'));self.assertEqual(f.sent(),before)
        f.poll(15001)
        self.assertEqual((f.g.background,f.r.pn.command),(2,0x44))
        f.respond(b'\0');f.respond(b'\0')
        self.assertEqual((f.r.present,f.r.active),(1,1))
        before=f.sent();f.send(gate.command(0x6f,bytes.fromhex('ffb0000410')))
        self.assertEqual(f.final()[0][10:],bytes.fromhex('6982'));self.assertEqual(f.sent(),before)

    def test_nonmatching_type_a_rejects_classic_without_rf(self):
        f=self.ready(sak=9);self.assertEqual(f.r.card.classic_candidate,0)
        before=f.sent();f.send(gate.command(0x6f,bytes.fromhex('ff82000006010203040506')))
        self.assertEqual(f.final()[0][7]&0xc0,0x40);self.assertEqual(f.sent(),before)
        self.assertNotIn(bytes.fromhex('010203040506'),bytes(f.r.pn.frame))
        self.assertEqual(bytes(f.ep2[:64]),bytes(64))

    def test_rejected_ccid_header_does_not_retain_key(self):
        f=self.ready();before=f.sent()
        f.send(gate.command(0x6f,bytes.fromhex('ff82000006010203040506'),p0=1))
        self.assertEqual(f.final()[0][7]&0xc0,0x40);self.assertEqual(f.sent(),before)
        self.assertEqual(bytes(f.r.pn.frame),bytes(len(f.r.pn.frame)))
        self.assertEqual(bytes(f.ep2[:64]),bytes(64))

    def test_failed_authentication_drops_key_and_reset_clears_pending(self):
        f=self.ready();self.load(f)
        self.assertEqual(self.exchange(f,bytes.fromhex('ff860000050100046000'),b'\x14'),bytes.fromhex('6300'))
        session=ClassicSession.in_dll(f.lib,'classic_session')
        self.assertEqual((session.key_loaded,bytes(session.key)),(0,bytes(6)))
        self.load(f)
        f.send(gate.command(0x6f,bytes.fromhex('ff860000050100046000')))
        f.lib.test_reset();f.poll()
        self.assertEqual((session.key_loaded,bytes(session.key)),(0,bytes(6)))
        self.assertEqual((f.r.present,f.r.active,f.g.powered),(0,0,0))

    def test_incomplete_key_request_timeout_wipes_receive_buffers(self):
        f=self.ready()
        partial=gate.command(0x6f,bytes.fromhex('ff82000006010203040506'))[:-4]
        f.send(partial)
        self.assertIn(bytes.fromhex('ff8200000601'),bytes(f.r.pn.frame))
        f.poll(1100)
        self.assertEqual(f.final()[0][7]&0xc0,0x40)
        self.assertEqual(bytes(f.r.pn.frame),bytes(len(f.r.pn.frame)))
        self.assertEqual(bytes(f.ep2[:64]),bytes(64))

    def test_malformed_pn_reply_drops_session_key_without_replay(self):
        f=self.ready();self.load(f)
        self.assertEqual(self.exchange(f,bytes.fromhex('ff860000050100046000'),b'\0'),bytes.fromhex('9000'))
        before=f.sent();self.assertEqual(self.exchange(f,bytes.fromhex('ffb0000410'),b'\0'+bytes(15)),bytes.fromhex('6300'))
        session=ClassicSession.in_dll(f.lib,'classic_session')
        self.assertEqual((session.key_loaded,bytes(session.key)),(0,bytes(6)))
        self.assertEqual(f.sent()[len(before):].count(bytes.fromhex('d440013004')),1)

    def test_abort_authentication_clears_key_and_never_replays(self):
        f=self.ready();self.load(f);before=f.sent()
        f.send(gate.command(0x6f,bytes.fromhex('ff860000050100046000')))
        f.poll();f.abort(sequence=7)
        session=ClassicSession.in_dll(f.lib,'classic_session')
        self.assertEqual((session.key_loaded,bytes(session.key),f.g.powered),(0,bytes(6),0))
        for payload in (gate.VERSION,b'',b'',b'',b''):f.respond(payload)
        self.assertEqual(f.final()[0][7]&0xc0,0)
        self.assertLessEqual(f.sent()[len(before):].count(bytes.fromhex('d440016004')),1)
        self.assertEqual(bytes(f.r.pn.frame),bytes(len(f.r.pn.frame)))

    def test_iso_dep_a_and_b_remain_available(self):
        for kind in (0,3):
            with self.subTest(kind=kind):
                f=self.fixture();f.setUp()
                for payload in (gate.VERSION,b'',b'',b'',b''): f.respond(payload)
                f.send(gate.command(0x62));f.respond(b'')
                if kind==3: f.respond(b'\0')
                f.respond(type_a() if kind==0 else type_b())
                self.assertEqual(f.final()[0][7]&0xc0,0)
                f.notifications();f.send(gate.command(0x6f,bytes.fromhex('00a4040000')))
                f.respond(b'\0\x90\0' if kind==0 else b'\0\x0a\x01\x90\0')
                self.assertEqual(f.final()[0][10:],bytes.fromhex('9000'))
