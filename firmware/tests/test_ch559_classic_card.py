# SPDX-License-Identifier: Apache-2.0
"""Synthetic Type A classification for the isolated CH559 experiment."""
import ctypes as c
from pathlib import Path
import subprocess
import tempfile
import unittest


class Card(c.Structure):
    _fields_=[('atr',c.c_uint8*20),('atr_length',c.c_uint8),('type',c.c_uint8),
              ('cid',c.c_uint8),('uid',c.c_uint8*10),('classic_candidate',c.c_uint8)]


class Ch559ClassicCardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='pakuri-classic-card-')
        cls.addClassCleanup(cls.tmp.cleanup)
        root=Path(__file__).resolve().parents[1]; out=Path(cls.tmp.name)/'card.so'
        subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-shared','-fPIC',
                        '-DMG_UID_PROFILE','-DMG_CH559','-DMG_CH559_CLASSIC',
                        '-DMG_SINGLETON','-DMG_COMPACT_ABI','-DMG_SOFT_B',
                        str(root/'src/card.c'),'-o',str(out)],check=True)
        cls.lib=c.CDLL(str(out))
        cls.lib.card_parse.argtypes=[c.POINTER(Card),c.c_uint8,c.POINTER(c.c_uint8),c.c_uint16]
        cls.lib.card_parse.restype=c.c_uint8
        cls.lib.card_clear.argtypes=[c.POINTER(Card)]

    def test_only_expected_shape_is_a_candidate(self):
        for atqa,sak,uid_length,expected in ((b'\x00\x04',8,4,1),(b'\x00\x44',8,4,0),
                                             (b'\x00\x04',9,4,0),(b'\x00\x04',0x18,4,0),
                                             (b'\x00\x04',8,7,0),(b'\x00\x04',8,10,0)):
            payload=bytes([1,1])+atqa+bytes([sak,uid_length])+bytes(range(uid_length))
            card=Card(); buf=(c.c_uint8*len(payload)).from_buffer_copy(payload)
            with self.subTest(atqa=atqa,sak=sak,uid_length=uid_length):
                self.assertEqual(self.lib.card_parse(c.byref(card),0,buf,len(payload)),0)
                self.assertEqual(card.classic_candidate,expected)
                self.lib.card_clear(c.byref(card))
                self.assertEqual(bytes(card),bytes(c.sizeof(card)))

    def test_malformed_and_absent_cannot_keep_candidate(self):
        for payload in (b'\0', bytes.fromhex('010100040804010203'), bytes.fromhex('02010004080401020304')):
            card=Card();card.classic_candidate=1
            buf=(c.c_uint8*len(payload)).from_buffer_copy(payload)
            self.assertNotEqual(self.lib.card_parse(c.byref(card),0,buf,len(payload)),0)
            self.assertEqual(card.classic_candidate,0)
