# SPDX-License-Identifier: Apache-2.0
"""実C reader+transport+codecを合成UARTと結合して検査。実カードは操作しない。"""
import ctypes as c
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_card import Card, type_a, type_b
from test_pn532_transport import State, ACK, SEND, ACK_WAIT, RESPONSE, DONE, FAILED
from test_pn532_frame import array, response


R_RECOVER, R_VERSION, R_SAM, R_PARAMETERS, R_RETRIES = range(1, 6)
R_IDLE, R_SCAN, R_PRESENCE, R_APDU, R_OFF, R_DONE, R_FAILED = range(6, 13)
VERSION = bytes.fromhex("32010607")


class Reader(c.Structure):
    _fields_ = [("pn", State), ("card", Card)] + [(name, c.c_uint8) for name in
                ("phase", "present", "active", "selected", "initialized", "error", "scan_type", "activate", "rf_status")]


class ReaderTests(unittest.TestCase):
    singleton = False
    extra_flags = ()
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="pakuri-reader-")
        cls.addClassCleanup(cls.tmp.cleanup)
        root = Path(__file__).resolve().parents[1]
        out = Path(cls.tmp.name) / "reader.so"
        sources = [root / "src" / (name + ".c") for name in
                   ("reader", "card", "pn532_transport", "pn532_frame")]
        if '-DMG_SOFT_B' in cls.extra_flags:sources.append(root/'src/isodep_b.c')
        if '-DMG_COMPACT_ABI' in cls.extra_flags:sources.append(root/'tests/compact_abi_exports.c')
        subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-shared", "-fPIC",
                        *(["-DMG_SINGLETON"] if cls.singleton else []), *cls.extra_flags,
                        "-fsanitize=undefined", "-fno-sanitize-recover=all",
                        *(str(p) for p in sources), str(root / "tests/transport_uart_mock.c"),
                        "-o", str(out)], check=True)
        cls.lib = c.CDLL(str(out))
        pointer = c.POINTER(Reader)
        for name in ("reader_init", "reader_recover", "reader_poll", "reader_presence", "reader_field_off"):
            getattr(cls.lib, name).argtypes = [pointer, c.c_uint16]
        cls.lib.reader_release.argtypes = [pointer]
        cls.lib.reader_scan.argtypes = [pointer, c.c_uint8, c.c_uint8, c.c_uint16]
        cls.lib.reader_exchange.argtypes = [pointer, c.POINTER(c.c_uint8), c.c_uint16, c.c_uint16]
        for name in ("reader_scan", "reader_presence", "reader_field_off", "reader_exchange"):
            getattr(cls.lib, name).restype = c.c_uint8
        cls.lib.test_feed.argtypes = [c.c_uint8]
        cls.lib.test_tx_at.argtypes = [c.c_uint16]
        cls.lib.test_tx_at.restype = c.c_uint8
        cls.lib.test_tx_length.restype = c.c_uint16

    def setUp(self):
        self.r = Reader.in_dll(self.lib, "reader_state") if self.singleton else Reader()
        self.now = 0
        self.lib.uart_init()
        self.lib.reader_init(c.byref(self.r), self.now)

    def poll(self, advance=1):
        self.now = (self.now + advance) & 65535
        self.lib.reader_poll(c.byref(self.r), self.now)

    def respond(self, payload):
        for _ in range(1000):
            if self.r.pn.phase == ACK_WAIT:
                break
            self.poll()
            self.assertNotEqual(self.r.phase, R_FAILED)
        else:
            self.fail("ACK待ちにならない")
        command = self.r.pn.command
        for byte in ACK + response(payload, command=(command + 1) & 255):
            self.lib.test_feed(byte)
        for _ in range(20):
            self.poll()
            if self.r.pn.phase not in (ACK_WAIT, RESPONSE):
                return
        self.fail("応答を消費できない")

    def initialize(self):
        self.respond(VERSION)
        self.assertEqual(self.r.phase, R_SAM)
        self.respond(b"")
        self.assertEqual(self.r.phase, R_PARAMETERS)
        self.respond(b"")
        self.assertEqual(self.r.phase, R_RETRIES)
        self.respond(b"")
        self.assertEqual((self.r.phase, self.r.initialized), (R_DONE, 1))
        self.release()

    def release(self):
        self.lib.reader_release(c.byref(self.r))

    def scan(self, kind=0, activate=1, payload=None):
        self.assertEqual(self.lib.reader_scan(c.byref(self.r), kind, activate, self.now), 0)
        self.respond((type_a() if kind == 0 else type_b()) if payload is None else payload)

    def exchange(self, apdu):
        return self.lib.reader_exchange(c.byref(self.r), array(apdu), len(apdu), self.now)

    def sent(self):
        return bytes(self.lib.test_tx_at(i) for i in range(self.lib.test_tx_length()))

    def test_initialize_checks_capabilities_and_uses_bounded_configuration(self):
        self.initialize()
        self.assertEqual(self.r.phase, R_IDLE)
        self.assertEqual((self.r.present, self.r.active, self.r.selected), (0, 0, 0))
        wire = self.sent()

        self.assertIn(bytes.fromhex("d414010000"), wire)
        self.assertIn(bytes.fromhex("d41214"), wire)
        self.assertIn(bytes.fromhex("d43205000000"), wire)

    def test_missing_type_b_support_is_not_initialized(self):
        self.respond(bytes.fromhex("32010601"))
        self.assertEqual((self.r.phase, self.r.initialized), (R_FAILED, 0))

    def test_type_a_b_activation_and_inactive_discovery(self):
        for kind in (0, 3):
            with self.subTest(kind=kind):
                self.setUp(); self.initialize(); self.scan(kind, activate=0)
                self.assertEqual((self.r.phase, self.r.present, self.r.active, self.r.selected), (R_DONE, 1, 0, 1))
                self.assertGreater(self.r.card.atr_length, 0)
                self.release()
                self.assertNotEqual(self.exchange(bytes(4)), 0)

    def test_presence_does_not_reselect_or_send_apdu(self):
        self.initialize(); self.scan(); self.release()
        before = len(self.sent())
        self.assertEqual(self.lib.reader_presence(c.byref(self.r), self.now), 0)
        self.respond(bytes.fromhex("00a2"))
        self.assertEqual((self.r.present, self.r.active, self.r.selected), (1, 1, 1))
        self.assertEqual(self.sent()[before:][5:8], bytes.fromhex("d442b2"))
        self.assertEqual(self.r.rf_status, 0)

    def test_type_b_presence_uses_selected_cid_and_accepts_ack_or_last_i_block(self):
        for cid in (0, 1, 14):
            for body in (bytes([0xAA,cid]), bytes([0xAB,cid]), bytes([0x0A,cid,0x90,0]),
                         bytes([0x1B,cid,0x90,0])):
                self.setUp();self.initialize();self.scan(3,payload=type_b(cid));self.release()
                before=len(self.sent())
                self.lib.reader_presence(c.byref(self.r),self.now)
                self.respond(b"\x00"+body)
                self.assertEqual((self.r.present,self.r.active,self.r.selected),(1,1,1))
                self.assertEqual(self.sent()[before:][5:9],bytes([0xD4,0x42,0xBA,cid]))

    def test_presence_rejects_wrong_cid_malformed_blocks_and_ack_payload(self):
        cases=[(3,x) for x in (b"",b"\x00",bytes.fromhex("00aa"),bytes.fromhex("00aa02"),
                 bytes.fromhex("00ba01"),bytes.fromhex("00aa0100"),bytes.fromhex("000e0100"),
                 bytes.fromhex("00a2"))]
        cases += [(0,x) for x in (bytes.fromhex("00aa01"),bytes.fromhex("00b2"),bytes.fromhex("00a200"))]
        for kind,payload in cases:
            self.setUp();self.initialize();self.scan(kind);self.release()
            self.lib.reader_presence(c.byref(self.r),self.now);self.respond(payload)
            self.assertEqual(self.r.phase,R_FAILED)
            self.assertEqual((self.r.present,self.r.active,self.r.selected),(0,0,0))

    def test_presence_raw_response_boundary_and_type_a_last_i_block(self):
        for kind,body in ((0,bytes([2])+bytes(261)),(3,bytes([0x0A,1])+bytes(260))):
            self.setUp();self.initialize();self.scan(kind);self.release()
            self.lib.reader_presence(c.byref(self.r),self.now)
            self.respond(b"\x00"+body)
            self.assertEqual(self.r.phase,R_DONE)
            self.assertEqual(self.r.present,1)
        self.setUp();self.initialize();self.scan();self.release()
        self.lib.reader_presence(c.byref(self.r),self.now)
        self.respond(bytes(264))
        self.assertEqual(self.r.phase,R_FAILED)
        self.assertEqual(self.r.present,0)

    def test_removal_invalidates_atr_and_prevents_old_apdu(self):
        self.initialize(); self.scan(); self.release()
        self.lib.reader_presence(c.byref(self.r), self.now)
        self.respond(b"\x01")
        self.assertEqual(self.r.rf_status, 1)
        self.assertEqual((self.r.present, self.r.active, self.r.selected, self.r.error), (0, 0, 0, 1))
        self.assertEqual(bytes(self.r.card.atr), bytes(20))
        self.release()
        self.assertNotEqual(self.exchange(bytes(4)), 0)
        self.scan(3, activate=0)
        self.assertEqual((self.r.card.type, self.r.active), (3, 0))

    def test_maximum_apdu_and_response_share_one_frame(self):
        self.initialize(); self.scan(); self.release()
        command = bytes([0, 0xA4, 4, 0, 255]) + bytes(256)
        self.r.pn.frame[11:11 + len(command)] = command
        data = c.cast(c.byref(self.r.pn.frame, 11), c.POINTER(c.c_uint8))
        self.assertEqual(self.lib.reader_exchange(c.byref(self.r), data, len(command), self.now), 0)
        self.assertEqual(self.r.pn.total, 274)
        self.assertEqual(bytes(self.r.pn.frame)[10:272], b"\1" + command)
        self.assertEqual(self.r.active, 0)
        reply = bytes(range(256)) + b"\x90\0"
        self.respond(b"\0" + reply)
        self.assertEqual((self.r.phase, self.r.active, self.r.pn.payload), (R_DONE, 1, 258))
        self.assertEqual(self.r.rf_status, 0)
        self.assertEqual(bytes(self.r.pn.frame)[self.r.pn.offset:][:258], reply)
        self.release()
        self.assertEqual(bytes(self.r.pn.frame), bytes(275))

    def test_short_in_place_apdu_moves_without_corrupting_payload(self):
        self.initialize(); self.scan(); self.release()
        command = bytes.fromhex("00a4040002010200")
        self.r.pn.frame[11:11 + len(command)] = command
        data = c.cast(c.byref(self.r.pn.frame, 11), c.POINTER(c.c_uint8))
        self.assertEqual(self.lib.reader_exchange(c.byref(self.r), data, len(command), self.now), 0)
        self.assertEqual(bytes(self.r.pn.frame)[7:8 + len(command)], b"\1" + command)
        self.respond(bytes.fromhex("009000"))
        self.assertEqual(self.r.active, 1)

    def test_invalid_apdu_does_not_send_or_destroy_valid_connection(self):
        self.initialize(); self.scan(); self.release()
        before = self.sent()
        self.assertEqual(self.exchange(bytes(7)), 3)
        self.assertEqual(self.sent(), before)
        self.assertEqual((self.r.phase, self.r.active), (R_IDLE, 1))

    def test_bad_controller_status_and_short_response_close_connection(self):
        for payload in (b"", b"\0", b"\0\x90", b"\x40\x90\0", b"\x80\x90\0", b"\x01", b"\x12"):
            with self.subTest(payload=payload):
                self.setUp(); self.initialize(); self.scan(); self.release()
                self.exchange(bytes(4)); self.respond(payload)
                self.assertEqual((self.r.phase, self.r.present, self.r.active, self.r.initialized), (R_FAILED, 0, 0, 0))
                self.assertEqual(self.r.rf_status, payload[0] if payload else 0xff)
                self.assertNotEqual(self.exchange(bytes(4)), 0)
                self.lib.reader_recover(c.byref(self.r), self.now)
                self.assertEqual(self.r.rf_status, 0xff)

    def test_cancel_recovery_never_replays_old_apdu(self):
        self.initialize(); self.scan(); self.release()
        self.exchange(bytes(4)); self.respond(bytes.fromhex("009000"))
        wire = self.sent()
        self.lib.reader_recover(c.byref(self.r), self.now)
        self.assertEqual((self.r.present, self.r.active), (0, 0))
        self.initialize()
        self.assertNotIn(bytes.fromhex("d44001"), self.sent()[len(wire):])
        self.assertNotEqual(self.exchange(bytes(4)), 0)

    def test_field_off_clears_activation_and_requires_fresh_scan(self):
        self.initialize(); self.scan(); self.release()
        self.assertEqual(self.lib.reader_scan(c.byref(self.r), 0, 1, self.now), 4)
        self.assertEqual(self.lib.reader_field_off(c.byref(self.r), self.now), 0)
        self.assertEqual((self.r.active, self.r.selected), (0, 0))
        self.respond(b""); self.release()
        self.assertNotEqual(self.exchange(bytes(4)), 0)
        self.scan(0, payload=b"\0")
        self.assertEqual((self.r.present, self.r.error), (0, 1))


class SingletonReaderTests(ReaderTests):
    singleton = True

    def test_foreign_instance_cannot_mutate_fixed_reader(self):
        self.initialize(); self.scan(); self.release()
        snapshot = bytes(self.r)
        other = Reader()
        self.assertEqual(self.lib.reader_scan(c.byref(other), 0, 1, self.now), 4)
        self.lib.reader_init(c.byref(other), self.now)
        self.lib.reader_poll(c.byref(other), self.now)
        self.lib.reader_recover(c.byref(other), self.now)
        self.lib.pn_transport_init.argtypes = [c.POINTER(State)]
        self.lib.pn_transport_init(c.byref(other.pn))
        self.lib.pn_transport_poll.argtypes = [c.POINTER(State), c.c_uint16]
        self.lib.pn_transport_poll(c.byref(other.pn), self.now)
        self.assertEqual(bytes(self.r), snapshot)


if __name__ == "__main__":
    unittest.main()
