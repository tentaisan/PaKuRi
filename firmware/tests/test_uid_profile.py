# SPDX-License-Identifier: Apache-2.0
"""UID profileの合成カード・CCID試験。実UIDは使わない。"""
import ctypes as c
import unittest
import test_gate as gate
import test_soft_b_reader as soft
from test_card import type_a
from test_pn532_transport import State


class UidCard(c.Structure):
    _fields_=[('atr',c.c_uint8*20),('atr_length',c.c_uint8),('type',c.c_uint8),
              ('cid',c.c_uint8),('uid',c.c_uint8*10)]


class UidReader(c.Structure):
    _fields_=[('pn',State),('card',UidCard)]+[(name,c.c_uint8) for name in
        ('phase','present','active','selected','initialized','error','scan_type','activate','rf_status')]


def gate_fixture():
    class Fixture(gate.GateTests):
        extra_flags=('-DMG_SOFT_B','-DMG_COMPACT_ABI','-DMG_UID_PROFILE')
        def setUp(self):
            super().setUp()
            self.r=UidReader.in_dll(self.lib,'reader_state')
    return Fixture


class UidProfileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture=gate_fixture();cls.fixture.setUpClass();cls.addClassCleanup(cls.fixture.doClassCleanups)

    def setup_reader(self,uid=b'\x11\x22\x33\x44'):
        f=self.fixture();f.setUp()
        for payload in (gate.VERSION,b'',b'',b'',b''):f.respond(payload)
        f.send(gate.command(0x62));f.respond(b'')
        f.respond(bytes([1,1,0,4,8,len(uid)])+uid)
        message,_=f.final()
        self.assertEqual(message[10:],bytes.fromhex('3b8f8001804f0ca000000306030000000000006b'))
        self.assertEqual((f.r.present,f.r.active,f.g.powered,f.r.card.type),(1,1,1,1))
        return f

    def test_uid_get_data_lengths_and_no_rf_command(self):
        for uid in (bytes([1,2,3,4]),bytes(range(7)),bytes(range(10))):
            f=self.setup_reader(uid)
            for le in (0,len(uid)-1,len(uid),len(uid)+2,255):
                with self.subTest(uid_length=len(uid),le=le):
                    before=f.sent();f.send(gate.command(0x6f,bytes((0xff,0xca,0,0,le))))
                    message,_=f.final();self.assertEqual(f.sent(),before)
                    if le and le<len(uid):expected=bytes((0x6c,len(uid)))
                    elif le>len(uid):expected=uid+bytes(le-len(uid))+b'\x62\x82'
                    else:expected=uid+b'\x90\x00'
                    self.assertEqual(message[10:],expected)

    def test_other_commands_rejected_without_rf(self):
        f=self.setup_reader();before=f.sent()
        for apdu in (bytes.fromhex('ff82000006ffffffffffff'),bytes.fromhex('ffa0000004deadbeef'),
                     bytes.fromhex('ffca010000'),bytes.fromhex('00a4040000')):
            f.send(gate.command(0x6f,apdu));message,_=f.final()
            self.assertEqual(message[7]&0xc0,0x40)
            self.assertEqual(f.sent(),before)

    def test_presence_two_pn_commands_and_removal_wipes_uid(self):
        f=self.setup_reader();f.notifications();f.poll(200)
        self.assertEqual((f.g.background,f.r.pn.command),(2,0x44))
        f.respond(b'\x00');self.assertEqual(f.r.pn.command,0x54)
        f.respond(b'\x00');self.assertEqual((f.r.present,f.r.active),(1,1))
        f.notifications();f.poll(200);self.assertEqual(f.r.pn.command,0x44)
        f.respond(b'\x00');self.assertEqual(f.r.pn.command,0x54)
        f.respond(b'\x01')
        self.assertEqual((f.r.present,f.r.active,f.g.powered),(0,0,0))
        self.assertEqual(bytes(f.r.card.uid),bytes(10))
        f.send(gate.command(0x6f,bytes.fromhex('ffca000000')));message,_=f.final()
        self.assertEqual(message[7]&0xc0,0x40)

    def test_pending_uid_request_never_returns_old_uid_after_removal(self):
        f=self.setup_reader();f.notifications();f.poll(200)
        self.assertEqual(f.r.pn.command,0x44)
        f.send(gate.command(0x6f,bytes.fromhex('ffca000000')))
        self.assertEqual((f.g.background,f.g.powered),(2,1))
        f.respond(b'\x00');self.assertEqual(f.r.pn.command,0x54)
        f.respond(b'\x01');message,_=f.final()
        self.assertEqual(message[7]&0xc0,0x40)
        self.assertNotIn(bytes.fromhex('11223344'),message)
        self.assertEqual(bytes(f.r.card.uid),bytes(10))

    def test_malformed_presence_fails_closed_and_wipes_uid(self):
        f=self.setup_reader();f.notifications();f.poll(200)
        self.assertEqual(f.r.pn.command,0x44)
        f.respond(b'\x00');self.assertEqual(f.r.pn.command,0x54)
        f.respond(b'\x00\x00')
        self.assertEqual((f.r.phase,f.r.present,f.r.active),(12,0,0))
        self.assertEqual(bytes(f.r.card.uid),bytes(10))

    def test_usb_reset_invalidates_storage_card_and_wipes_uid(self):
        f=self.setup_reader();f.lib.test_reset();f.poll()
        self.assertEqual((f.r.present,f.r.active,f.g.powered),(0,0,0))
        self.assertEqual(bytes(f.r.card.uid),bytes(10))

    def test_storage_parser_rejects_malformed_lengths_without_retaining_uid(self):
        f=self.fixture();f.setUp()
        parse=f.lib.card_parse
        parse.argtypes=[c.POINTER(UidCard),c.c_uint8,c.POINTER(c.c_uint8),c.c_uint16]
        parse.restype=c.c_uint8
        for payload in (bytes.fromhex('0101000408041122'),bytes.fromhex('0101000408051122334455'),
                        bytes.fromhex('0101000408041122334400'),bytes.fromhex('01020004080411223344')):
            card=UidCard();card.uid[:]=bytes([0xa5])*10
            data=(c.c_uint8*len(payload)).from_buffer_copy(payload)
            self.assertEqual(parse(c.byref(card),0,data,len(payload)),3)
            self.assertEqual(bytes(card.uid),bytes(10))

    def test_iso_dep_a_continues_to_forward_apdu(self):
        f=self.fixture();f.setUp()
        for payload in (gate.VERSION,b'',b'',b'',b''):f.respond(payload)
        f.power_on(0);f.send(gate.command(0x6f,bytes.fromhex('00a4040000')))
        self.assertEqual(f.r.pn.command,0x40)
        f.respond(b'\x00\x90\x00');message,_=f.final();self.assertEqual(message[10:],b'\x90\x00')


class UidIsoDepRegressionTests(soft.SoftwareGateTests):
    @classmethod
    def setUpClass(cls):
        cls.fixture=gate_fixture();cls.fixture.setUpClass();cls.addClassCleanup(cls.fixture.doClassCleanups)
