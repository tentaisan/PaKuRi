# SPDX-License-Identifier: AGPL-3.0-only
"""ManeKey試験から2026-10-25に改変。独立CCID C実装の境界/USB完了試験。"""
import ctypes as c
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest


class Rx(c.Structure):
    _fields_ = [("maximum", c.c_uint16), ("total", c.c_uint16), ("emitted", c.c_uint16),
                ("header", c.c_uint8 * 10), ("used", c.c_uint8), ("stopped", c.c_uint8)]


class Tx(c.Structure):
    _fields_ = [("total", c.c_uint16), ("copied", c.c_uint16),
                ("used", c.c_uint8), ("waiting", c.c_uint8),
                ("complete", c.c_uint8), ("stopped", c.c_uint8)]


def array(data):
    return (c.c_uint8 * len(data)).from_buffer_copy(data)


def message(size):
    return struct.pack("<BIBBBBB", 0x6f, size, 0, 9, 0, 0, 0) + bytes(i % 251 for i in range(size))


class CcidStreamTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory(prefix="pakuri-ccid-")
        source = Path(__file__).resolve().parents[1] / "src/ccid_packet.c"
        library = Path(cls.directory.name) / "stream.so"
        subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-shared", "-fPIC",
                        "-fsanitize=undefined", "-fno-sanitize-recover=all", str(source),
                        "-o", str(library)], check=True)
        cls.lib = c.CDLL(str(library))
        p = c.POINTER(c.c_uint8)
        cls.lib.ccid_rx_init.argtypes = [c.POINTER(Rx), c.c_uint16]
        cls.lib.ccid_rx_push.argtypes = [c.POINTER(Rx), p, c.c_uint8, p, p, p]
        cls.lib.ccid_rx_stop.argtypes = [c.POINTER(Rx)]
        cls.lib.ccid_tx_init.argtypes = [c.POINTER(Tx), c.c_uint16, p]
        cls.lib.ccid_tx_push.argtypes = [c.POINTER(Tx), p, c.c_uint8, p]
        cls.lib.ccid_tx_delivered.argtypes = [c.POINTER(Tx), p]
        cls.lib.ccid_tx_stop.argtypes = [c.POINTER(Tx), p]
        for name in ("ccid_rx_push", "ccid_tx_init", "ccid_tx_push", "ccid_tx_delivered"):
            getattr(cls.lib, name).restype = c.c_uint8

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def push(self, rx, data):
        consumed, written = c.c_uint8(), c.c_uint8()
        out = array(bytes([0xa5]) * 64)
        ok = self.lib.ccid_rx_push(c.byref(rx), array(data), len(data),
                                   c.byref(consumed), out, c.byref(written))
        self.assertLessEqual(written.value, 54)
        self.assertEqual(bytes(out)[54:], bytes([0xa5]) * 10)
        return ok, consumed.value, bytes(out)[:written.value]

    def test_split_headers_and_large_messages_stream_without_message_storage(self):
        for size in (0, 1, 44, 54, 64, 255, 1024, 7609, 65525):
            for first in (1, 5, 9, 10, 64):
                rx = Rx()
                data = message(size)
                self.lib.ccid_rx_init(c.byref(rx), len(data))
                packets = [data[:first]] + [data[i:i+64] for i in range(first, len(data), 64)]
                result = bytearray()
                for packet in packets:
                    while packet:
                        ok, used, output = self.push(rx, packet)
                        self.assertEqual(ok, 1)
                        self.assertGreater(used, 0)
                        result += output
                        packet = packet[used:]
                self.assertEqual(bytes(result), data)
                self.assertEqual((rx.emitted, rx.total), (len(data), len(data)))
                self.lib.ccid_rx_stop(c.byref(rx))
                self.assertEqual(bytes(rx.header), bytes(10))

    def test_oversize_overflow_and_trailing_bytes_fail_closed(self):
        for data, maximum in ((message(20), 29),
                              (b"\x6f\0\0\1\0" + bytes(5), 65535),
                              (message(0) + b"x", 1024),
                              (message(65525)[:65], 65535)):
            rx = Rx()
            self.lib.ccid_rx_init(c.byref(rx), maximum)
            self.assertEqual(self.push(rx, data)[0], 0)
            self.assertEqual(rx.stopped, 1)
            self.assertEqual(bytes(rx.header), bytes(10))
            self.assertEqual(self.push(rx, message(0))[0], 0)

    def test_usb_completion_and_zlp_gate_final_response_release(self):
        for total in (10, 63, 64, 65, 128, 7609):
            tx, packet = Tx(), array(bytes(64))
            data = message(total - 10)
            self.assertEqual(self.lib.ccid_tx_init(c.byref(tx), total, packet), 1)
            result, lengths, offset = bytearray(), [], 0
            while not tx.complete:
                if not tx.waiting:
                    piece = data[offset:offset+54]
                    n = self.lib.ccid_tx_push(c.byref(tx), array(piece), len(piece), packet)
                    self.assertGreater(n, 0)
                    offset += n
                if tx.waiting:
                    lengths.append(tx.used)
                    result += bytes(packet)[:tx.used]
                    held = bytes(packet)
                    self.assertEqual(self.lib.ccid_tx_push(c.byref(tx), array(b"x"), 1, packet), 0)
                    self.assertEqual(bytes(packet), held)
                    self.assertEqual(tx.complete, 0)
                    self.assertEqual(self.lib.ccid_tx_delivered(c.byref(tx), packet), 1)
                    self.assertEqual(bytes(packet), bytes(64))
            self.assertEqual(bytes(result), data)
            self.assertEqual(lengths[-1], total % 64)
            self.assertEqual(self.lib.ccid_tx_delivered(c.byref(tx), packet), 0)

    def test_tx_overrun_and_explicit_stop_wipe_packet(self):
        tx, packet = Tx(), array(bytes(64))
        self.assertEqual(self.lib.ccid_tx_init(c.byref(tx), 9, packet), 0)
        self.lib.ccid_tx_init(c.byref(tx), 10, packet)
        self.assertEqual(self.lib.ccid_tx_push(c.byref(tx), array(bytes(11)), 11, packet), 0)
        self.assertEqual(tx.stopped, 1)
        self.assertEqual(bytes(packet), bytes(64))
        self.lib.ccid_tx_init(c.byref(tx), 100, packet)
        self.assertEqual(self.lib.ccid_tx_push(c.byref(tx), array(b"secret"), 6, packet), 6)
        self.lib.ccid_tx_stop(c.byref(tx), packet)
        self.assertEqual(bytes(packet), bytes(64))


if __name__ == "__main__":
    unittest.main()
