# SPDX-License-Identifier: Apache-2.0
"""4K candidate integration with synthetic card and PN532 responses only."""
import ctypes as c
import unittest
import test_gate as gate
from test_ch559_classic_gate import CandidateReader

class Classic4KGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        class Fixture(gate.GateTests):
            extra_flags=('-DMG_SOFT_B','-DMG_COMPACT_ABI','-DMG_UID_PROFILE',
                         '-DMG_CH559','-DMG_CH559_CLASSIC','-DMG_CLASSIC_STACK_AUTO',
                         '-DMG_CH559_FELICA','-DMG_CLASSIC_4K','-DMG_CLASSIC_7B')
            def setUp(self):
                super().setUp();self.r=CandidateReader.in_dll(self.lib,'reader_state')
        cls.fixture=Fixture;Fixture.setUpClass();cls.addClassCleanup(Fixture.doClassCleanups)

    def test_4k_upper_sector_and_trailer_protection(self):
        f=self.fixture();f.setUp()
        for payload in (gate.VERSION,b'',b'',b'',b''):f.respond(payload)
        f.send(gate.command(0x62));f.respond(b'')
        f.respond(bytes.fromhex('01010002180401020304'))
        self.assertEqual(f.final()[0][7]&0xc0,0)
        self.assertEqual(f.r.card.classic_candidate,2);f.notifications()
        f.send(gate.command(0x6f,bytes.fromhex('ff82000006010203040506')))
        self.assertEqual(f.final()[0][10:],bytes.fromhex('9000'))
        f.send(gate.command(0x6f,bytes.fromhex('ff860000050100806000')))
        f.respond(b'\0');self.assertEqual(f.final()[0][10:],bytes.fromhex('9000'))
        f.send(gate.command(0x6f,bytes.fromhex('ffb0008e10')))
        f.respond(b'\0'+bytes(16));self.assertEqual(f.final()[0][10:],bytes(16)+bytes.fromhex('9000'))
        before=f.sent()
        payload=bytes(range(16))
        f.send(gate.command(0x6f,bytes.fromhex('ffd6008e10')+payload))
        f.respond(b'\0');self.assertEqual(f.final()[0][10:],bytes.fromhex('9000'))
        self.assertIn(bytes.fromhex('d44001a08e')+payload,f.sent()[len(before):])
        before=f.sent()
        f.send(gate.command(0x6f,bytes.fromhex('ffd6008f10')+bytes(16)))
        self.assertEqual(f.final()[0][10:],bytes.fromhex('6986'))
        self.assertEqual(f.sent(),before)
        f.send(gate.command(0x6f,bytes.fromhex('ffb0009010')))
        self.assertEqual(f.final()[0][10:],bytes.fromhex('6982'))

    def test_seven_byte_uid_is_complete_but_authentication_uses_cl2(self):
        for atqa,sak,kind in ((0x44,0x08,1),(0x42,0x18,2)):
            with self.subTest(kind=kind):
                f=self.fixture();f.setUp()
                for payload in (gate.VERSION,b'',b'',b'',b''):f.respond(payload)
                f.send(gate.command(0x62));f.respond(b'')
                f.respond(bytes([1,1,0,atqa,sak,7,1,2,3,4,5,6,7]))
                self.assertEqual(f.final()[0][7]&0xc0,0)
                self.assertEqual(f.r.card.classic_candidate,kind);f.notifications()
                f.send(gate.command(0x6f,bytes.fromhex('ffca000000')))
                self.assertEqual(f.final()[0][10:],bytes(range(1,8))+bytes.fromhex('9000'))
                f.send(gate.command(0x6f,bytes.fromhex('ff82000006010203040506')));f.final()
                before=f.sent()
                f.send(gate.command(0x6f,bytes.fromhex('ff860000050100046000')))
                f.respond(b'\0');self.assertEqual(f.final()[0][10:],bytes.fromhex('9000'))
                self.assertIn(bytes.fromhex('d44001600401020304050604050607'),f.sent()[len(before):])

    def test_ten_byte_uid_remains_readable_without_classic_access(self):
        f=self.fixture();f.setUp()
        for payload in (gate.VERSION,b'',b'',b'',b''):f.respond(payload)
        f.send(gate.command(0x62));f.respond(b'')
        f.respond(bytes([1,1,0,0x44,8,10])+bytes(range(10)))
        self.assertEqual(f.final()[0][7]&0xc0,0)
        self.assertEqual(f.r.card.classic_candidate,0);f.notifications()
        f.send(gate.command(0x6f,bytes.fromhex('ffca000000')))
        self.assertEqual(f.final()[0][10:],bytes(range(10))+bytes.fromhex('9000'))
        before=f.sent();f.send(gate.command(0x6f,bytes.fromhex('ff82000006010203040506')))
        self.assertEqual(f.final()[0][7]&0xc0,0x40);self.assertEqual(f.sent(),before)
