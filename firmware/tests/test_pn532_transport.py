# SPDX-License-Identifier: Apache-2.0
"""実C通信状態機械の取消・期限・復旧・buffer所有権を合成UARTで検証。"""
import ctypes as c
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_pn532_frame import array, response


class State(c.Structure):
    _fields_ = [("frame", c.c_uint8 * 275)] + [
        (name, c.c_uint16) for name in
        ("total", "cursor", "expected", "offset", "payload", "bound", "deadline", "quiet_since")
    ] + [(name, c.c_uint8) for name in ("phase", "command", "error", "verifying", "support")]


ACK = bytes.fromhex("0000ff00ff00")
VERSION = response(bytes.fromhex("32010607"))
CLOSED, READY, SEND, FINISH, ACK_WAIT, RESPONSE, DONE, FAILED = range(8)


class TransportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="pakuri-transport-")
        cls.addClassCleanup(cls.tmp.cleanup)
        root = Path(__file__).resolve().parents[1]
        out = Path(cls.tmp.name) / "transport.so"
        subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-shared",
                        "-fPIC", "-fsanitize=undefined", "-fno-sanitize-recover=all",
                        *getattr(cls, 'extra_flags', ()),
                        str(root / "src/pn532_transport.c"), str(root / "src/pn532_frame.c"),
                        str(root / "tests/transport_uart_mock.c"), "-o", str(out)], check=True)
        cls.lib = c.CDLL(str(out))
        state, byte = c.POINTER(State), c.POINTER(c.c_uint8)
        cls.lib.pn_transport_init.argtypes = [state]
        cls.lib.pn_transport_begin.argtypes = [state, c.c_uint8, byte, c.c_uint16,
                                               c.c_uint16, c.c_uint16, c.c_uint16]
        cls.lib.pn_transport_begin.restype = c.c_uint8
        cls.lib.pn_transport_poll.argtypes = [state, c.c_uint16]
        cls.lib.pn_transport_recover.argtypes = [state, c.c_uint16]
        cls.lib.pn_transport_release.argtypes = [state]
        cls.lib.test_feed.argtypes = [c.c_uint8]
        cls.lib.test_tx_at.argtypes = [c.c_uint16]
        cls.lib.test_tx_at.restype = c.c_uint8
        cls.lib.test_tx_length.restype = c.c_uint16

    def setUp(self):
        self.state = State()
        self.now = 0
        self.lib.uart_init()
        self.lib.pn_transport_init(c.byref(self.state))

    def poll(self, advance=1):
        self.now = (self.now + advance) & 65535
        self.lib.pn_transport_poll(c.byref(self.state), self.now)

    def until(self, phase, limit=1200):
        for _ in range(limit):
            if self.state.phase == phase:
                return
            self.poll()
            if self.state.phase == FAILED:
                self.fail(f"通信失敗: error={self.state.error}")
        self.fail(f"phase {phase}へ進まない: {self.state.phase}")

    def feed(self, data):
        for byte in data:
            self.lib.test_feed(byte)

    def sent(self):
        return bytes(self.lib.test_tx_at(i) for i in range(self.lib.test_tx_length()))

    def recover(self):
        self.lib.pn_transport_recover(c.byref(self.state), self.now)
        self.until(SEND)
        self.assertEqual(self.state.command, 2)
        self.assertEqual(self.state.verifying, 1)
        self.until(ACK_WAIT)
        self.feed(ACK + VERSION)
        self.poll()
        self.assertEqual(self.state.phase, READY)
        self.assertEqual(self.state.error, 0)

    def begin(self, command=0x40, data=b"\x01\x00\xa4", bound=259, timeout=1000):
        return self.lib.pn_transport_begin(c.byref(self.state), command, array(data),
                                            len(data), bound, self.now, timeout)

    def test_closed_initial_state_requires_verified_recovery(self):
        self.assertEqual(self.begin(), 32)
        self.recover()
        self.assertEqual(self.sent(), b"\x55" + ACK + bytes.fromhex("0000ff02fed4022a00"))
        self.assertEqual(bytes(self.state.frame), bytes(275))

    def test_full_extended_response_retained_until_release(self):
        self.recover()
        self.assertEqual(self.begin(bound=263), 0)
        self.until(ACK_WAIT)
        self.feed(ACK)
        self.poll()
        data = bytes(i % 251 for i in range(263))
        frame = response(data, command=0x41)
        for at in range(0, len(frame), 17):
            self.feed(frame[at:at + 17]); self.poll()
        self.assertEqual(self.state.phase, DONE)
        self.assertEqual(bytes(self.state.frame)[self.state.offset:][:self.state.payload], data)
        retained = bytes(self.state.frame)
        self.assertEqual(self.begin(), 32)
        self.assertEqual(bytes(self.state.frame), retained)
        self.lib.pn_transport_release(c.byref(self.state))
        self.assertEqual(self.state.phase, READY)
        self.assertEqual(bytes(self.state.frame), bytes(275))

    def test_cancel_each_tx_prefix_never_replays_valid_command(self):
        for sent_prefix in range(13):
            with self.subTest(sent_prefix=sent_prefix):
                self.setUp(); self.recover()
                before = len(self.sent())
                self.assertEqual(self.begin(), 0)
                original = bytes(self.state.frame)[:self.state.total]
                for _ in range(sent_prefix):
                    self.poll()
                self.recover()
                outgoing = self.sent()[before:]
                self.assertEqual(outgoing.count(original), 0 if sent_prefix <= len(original)-2 else 1)
                self.assertEqual(outgoing.count(bytes.fromhex("0000ff02fed4022a00")), 1)

    def test_response_cancel_discards_racing_old_response(self):
        self.recover(); self.begin(); self.until(ACK_WAIT)
        self.feed(ACK); self.poll()
        self.assertEqual(self.state.phase, RESPONSE)
        self.feed(response(b"\x00\x90\x00", command=0x41)[:7]); self.poll()
        before = len(self.sent())
        self.lib.pn_transport_recover(c.byref(self.state), self.now)
        self.feed(response(b"\x00\x90\x00", command=0x41))
        self.until(SEND); self.until(ACK_WAIT)
        self.feed(ACK + VERSION); self.poll()
        self.assertEqual(self.state.phase, READY)
        self.assertEqual(self.sent()[before:], b"\x55" + ACK + bytes.fromhex("0000ff02fed4022a00"))

    def test_timeout_precedes_queued_response_and_wraps_clock(self):
        self.recover()
        self.now = 65530
        self.begin(timeout=100)
        self.until(ACK_WAIT)
        self.feed(ACK + response(b"\0", command=0x41))
        self.now = self.state.deadline
        self.poll(0)
        self.assertEqual((self.state.phase, self.state.error), (FAILED, 33))
        self.assertEqual(self.begin(), 32)
        self.recover()

    def test_wrong_ack_frame_bound_and_firmware_close_link(self):
        for incoming, error in ((b"\x01", 35),
                                (ACK + response(b"ab", command=0x41), 37),
                                (ACK + response(b"a", command=0x43), 9)):
            with self.subTest(error=error):
                self.setUp(); self.recover(); self.begin(bound=1); self.until(ACK_WAIT)
                self.feed(incoming); self.poll()
                self.assertEqual((self.state.phase, self.state.error), (FAILED, error))
                self.recover()
        self.lib.pn_transport_recover(c.byref(self.state), self.now)
        self.until(SEND); self.until(ACK_WAIT)
        self.feed(ACK + response(b"\x31\x01\x06\x07")); self.poll()
        self.assertEqual((self.state.phase, self.state.error), (FAILED, 38))
        self.recover()

    def test_tx_buffer_held_until_last_byte_finishes(self):
        self.recover(); self.begin(); self.until(FINISH)
        retained = bytes(self.state.frame)
        self.lib.test_set_idle(0)
        self.feed(ACK)
        self.poll()
        self.assertEqual(self.state.phase, FINISH)
        self.assertEqual(bytes(self.state.frame), retained)
        self.lib.test_set_idle(1); self.poll()
        self.assertEqual(self.state.phase, RESPONSE)

    def test_overflow_and_unsolicited_bytes_require_recovery(self):
        self.recover()
        self.lib.test_set_fault(1); self.poll()
        self.assertEqual((self.state.phase, self.state.error), (FAILED, 34))
        self.recover()
        self.feed(b"x")
        self.assertEqual(self.begin(), 34)
        self.assertEqual(self.state.phase, FAILED)
        self.recover()

    def test_uart_error_34_has_multiple_distinct_pre_send_causes(self):


        for cause in ('rx_fault', 'tx_busy', 'pending_rx'):
            with self.subTest(cause=cause):
                self.setUp(); self.recover()
                if cause == 'rx_fault':
                    self.lib.test_set_fault(1)
                elif cause == 'tx_busy':
                    self.lib.test_set_idle(0)
                else:
                    self.feed(b'x')
                sent_before = self.sent()
                self.assertEqual(self.begin(), 34)
                self.assertEqual((self.state.phase, self.state.error), (FAILED, 34))
                self.assertEqual(self.sent(), sent_before)
    def test_recovery_has_finite_deadline_and_cannot_extend_it(self):
        self.lib.pn_transport_recover(c.byref(self.state), self.now)
        deadline = self.state.deadline
        for _ in range(1100):
            self.feed(b"x")
            self.lib.pn_transport_recover(c.byref(self.state), self.now)
            self.poll()
            if self.state.phase == FAILED:
                break
            self.assertEqual(self.state.deadline, deadline)
        self.assertEqual((self.state.phase, self.state.error), (FAILED, 33))

    def test_partial_tx_recovery_poison_is_idempotent_after_timeout(self):
        self.recover(); self.begin(); self.poll()
        self.lib.pn_transport_recover(c.byref(self.state), self.now)
        poisoned = bytes(self.state.frame)
        self.now = self.state.deadline; self.poll(0)
        self.assertEqual(self.state.phase, FAILED)
        self.lib.pn_transport_recover(c.byref(self.state), self.now)
        self.assertEqual(bytes(self.state.frame), poisoned)
        self.recover()

    def test_extra_data_after_response_is_not_next_request(self):
        self.recover(); self.begin(); self.until(ACK_WAIT)
        self.feed(ACK + response(b"\0", command=0x41) + b"x"); self.poll()
        self.assertEqual((self.state.phase, self.state.error), (FAILED, 11))


class TransportDiagnosticTests(TransportTests):
    extra_flags = ('-DMG_UART_DIAGNOSTIC',)

    def test_reason_and_phase_are_latched_without_uart_bytes(self):
        diagnostic = c.c_uint8.in_dll(self.lib, 'pn_uart_diagnostic')
        self.assertEqual(diagnostic.value, 0)
        for cause, expected in (('rx_fault', 0x11), ('tx_busy', 0x21), ('pending_rx', 0x31)):
            with self.subTest(cause=cause):
                self.setUp(); self.recover()
                if cause == 'rx_fault': self.lib.test_set_fault(1)
                elif cause == 'tx_busy': self.lib.test_set_idle(0)
                else: self.feed(b'\xa5')
                self.assertEqual(self.begin(), 34)
                self.assertEqual(diagnostic.value, expected)
        self.setUp(); self.recover(); self.begin(); self.until(SEND)
        self.feed(b'\xa5'); self.poll()
        self.assertEqual(diagnostic.value, 0x32)

    def test_timeout_records_phase_and_keeps_existing_error(self):
        diagnostic = c.c_uint8.in_dll(self.lib, 'pn_uart_diagnostic')
        self.recover(); self.begin(); self.until(ACK_WAIT)
        self.now = self.state.deadline; self.poll(0)
        self.assertEqual((self.state.phase, self.state.error, diagnostic.value), (FAILED, 33, 0x44))


if __name__ == "__main__":
    unittest.main()
