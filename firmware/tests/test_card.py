# SPDX-License-Identifier: Apache-2.0
"""合成activation応答の境界・PC/SC ATR・短APDU形式を実Cで検査。"""
import ctypes as c
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_pn532_frame import array


class Card(c.Structure):
    _fields_ = [("atr", c.c_uint8 * 20), ("atr_length", c.c_uint8), ("type", c.c_uint8), ("cid", c.c_uint8)]


def type_a(historical=b"", uid_length=4, t0=0x08, optional=b""):
    ats = bytes([2 + len(optional) + len(historical), t0]) + optional + historical
    return bytes([1, 1, 0, 4, 0x20, uid_length]) + bytes(range(uid_length)) + ats


def type_b(cid=1):
    return bytes.fromhex("010150010203041122334400810101") + bytes([0x50 | cid])


class CardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="pakuri-card-")
        cls.addClassCleanup(cls.tmp.cleanup)
        out = Path(cls.tmp.name) / "card.so"
        source = Path(__file__).resolve().parents[1] / "src/card.c"
        subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-shared", "-fPIC",
                        "-fsanitize=undefined", "-fno-sanitize-recover=all", *getattr(cls,"extra_flags",()), str(source),
                        "-o", str(out)], check=True)
        cls.lib = c.CDLL(str(out))
        cls.lib.card_parse.argtypes = [c.POINTER(Card), c.c_uint8, c.POINTER(c.c_uint8), c.c_uint16]
        cls.lib.card_parse.restype = c.c_uint8
        cls.lib.card_short_apdu.argtypes = [c.POINTER(c.c_uint8), c.c_uint16]
        cls.lib.card_short_apdu.restype = c.c_uint8

    def parse(self, kind, reply):
        card = Card()
        card.atr[:] = bytes([0xA5]) * 20
        result = self.lib.card_parse(c.byref(card), kind, array(reply), len(reply))
        atr = bytes(card.atr[:card.atr_length])
        if result:
            self.assertEqual(bytes(card.atr), bytes(20))
            self.assertEqual(card.atr_length, 0)
            self.assertEqual(card.cid, 0)
        else:
            checksum = 0
            for byte in atr[1:]:
                checksum ^= byte
            self.assertEqual(checksum, 0)
        return result, atr

    def test_type_a_historical_bytes_without_uid_or_optional_ats(self):
        for uid in (4, 7, 10):
            for historical in (b"", b"\x80\x01", bytes(range(15))):
                reply = type_a(historical, uid, 0x78, b"\x11\x40\x02")
                result, atr = self.parse(0, reply)
                self.assertEqual(result, 0)
                self.assertEqual(atr[:4], bytes([0x3B, 0x80 | len(historical), 0x80, 1]))
                self.assertEqual(atr[4:-1], historical)
        self.assertEqual(self.parse(0, type_a())[1], bytes.fromhex("3b80800101"))

    def test_type_b_application_protocol_and_mbli_mapping(self):
        result, atr = self.parse(3, type_b())
        self.assertEqual(result, 0)
        self.assertEqual(atr[4:-1], bytes.fromhex("1122334400810150"))
        self.assertEqual(len(atr), 13)
        self.assertEqual(self.parse(3, type_b(15))[0], 3)

    def test_absent_unsupported_and_invalid_do_not_keep_atr(self):
        self.assertEqual(self.parse(0, b"\0")[0], 1)
        non_iso = bytearray(type_a()[:-2]); non_iso[4] = 0
        self.assertEqual(self.parse(0, bytes(non_iso))[0], 2)
        non_iso = bytearray(type_b()); non_iso[12] = 0x80
        self.assertEqual(self.parse(3, bytes(non_iso))[0], 2)
        self.assertEqual(self.parse(1, type_b())[0], 3)

    def test_activation_truncation_trailing_and_target_count(self):
        for kind, reply in ((0, type_a()), (3, type_b())):
            for length in range(len(reply)):
                self.assertNotEqual(self.parse(kind, reply[:length])[0], 0)
            self.assertEqual(self.parse(kind, reply + b"\0")[0], 3)
            for count in (0, 2, 255):
                self.assertEqual(self.parse(kind, bytes([count]) + reply[1:])[0], 3)
            self.assertEqual(self.parse(kind, reply[:1] + b"\x02" + reply[2:])[0], 3)

    def test_bad_ats_boundaries_and_reserved_fields(self):
        for reply in (type_a(bytes(16)), type_a(t0=0x80), type_a(t0=0x09),
                      type_a(t0=0x10), type_a(t0=0x20), type_a(t0=0x40),
                      type_a(t0=0x10, optional=b"\x08"),
                      type_a(t0=0x20, optional=b"\xf0"),
                      type_a(t0=0x20, optional=b"\x0f"),
                      type_a(t0=0x40, optional=b"\x80"),
                      type_a(uid_length=5)):
            self.assertEqual(self.parse(0, reply)[0], 3)
        bad = bytearray(type_b()); bad[14] = 0
        self.assertEqual(self.parse(3, bytes(bad))[0], 3)
        bad = bytearray(type_b()); bad[12] = 0x91
        self.assertEqual(self.parse(3, bytes(bad))[0], 3)

    def test_short_apdu_all_cases_and_261_byte_boundary(self):
        for data in (bytes(4), bytes(5), b"\x00\xa4\x04\x00\x01\x01",
                     b"\x00\xa4\x04\x00\x01\x01\x00",
                     bytes([0, 0xA4, 4, 0, 255]) + bytes(256)):
            self.assertEqual(self.lib.card_short_apdu(array(data), len(data)), 1)
        for data in (b"", bytes(3), bytes(6), bytes(7),
                     b"\x00\xa4\x04\x00\x02\x01", bytes(262)):
            self.assertEqual(self.lib.card_short_apdu(array(data), len(data)), 0)


if __name__ == "__main__":
    unittest.main()
