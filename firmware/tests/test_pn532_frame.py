# SPDX-License-Identifier: Apache-2.0
"""実C codecをnative/UBSanで検査。公開vectorと独立生成した境界frameを使用。"""
import ctypes as c
from pathlib import Path
import subprocess
import tempfile
import unittest


def array(data):
    return (c.c_uint8 * len(data)).from_buffer_copy(data)


def response(data, direction=0xD5, command=3):
    packet = bytes([direction, command]) + data
    if len(packet) <= 255:
        prefix = bytes([0, 0, 255, len(packet), -len(packet) & 255])
    else:
        high, low = divmod(len(packet), 256)
        prefix = bytes([0, 0, 255, 255, 255, high, low, -(high + low) & 255])
    return prefix + packet + bytes([-sum(packet) & 255, 0])


class Pn532FrameTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="pakuri-pn532-")
        cls.addClassCleanup(cls.tmp.cleanup)
        out = Path(cls.tmp.name) / "frame.so"
        src = Path(__file__).resolve().parents[1] / "src/pn532_frame.c"
        subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-shared",
                        "-fPIC", "-fsanitize=undefined", "-fno-sanitize-recover=all",
                        *getattr(cls,"extra_flags",()), str(src), "-o", str(out)], check=True)
        cls.lib = c.CDLL(str(out))
        p, size = c.POINTER(c.c_uint8), c.POINTER(c.c_uint16)
        cls.lib.pn532_encode.argtypes = [c.c_uint8, p, c.c_uint16, p, c.c_uint16, size]
        cls.lib.pn532_decode.argtypes = [c.c_uint8, p, c.c_uint16, size, size]
        cls.lib.pn532_frame_length.argtypes = [p, c.c_uint16, size]
        for name in ("pn532_encode", "pn532_decode", "pn532_frame_length"):
            getattr(cls.lib, name).restype = c.c_uint8

    def decode(self, frame, command=2):
        offset, length = c.c_uint16(), c.c_uint16()
        status = self.lib.pn532_decode(command, array(frame), len(frame),
                                       c.byref(offset), c.byref(length))
        return status, frame[offset.value:offset.value + length.value]

    def test_published_firmware_version_vectors(self):
        out, total = array(bytes(275)), c.c_uint16()
        self.assertEqual(self.lib.pn532_encode(2, array(b""), 0, out, 275, c.byref(total)), 0)
        self.assertEqual(bytes(out)[:total.value], bytes.fromhex("0000ff02fed4022a00"))
        self.assertEqual(self.decode(bytes.fromhex("0000ff06fad50332010507e900")),
                         (0, bytes.fromhex("32010507")))

    def test_normal_extended_and_maximum_boundaries(self):
        for length in (0, 1, 252, 253, 254, 258, 262, 263):
            with self.subTest(length=length):
                data = bytes(i % 251 for i in range(length))
                frame = response(data)
                self.assertEqual(self.decode(frame), (0, data))
                out, total = array(bytes(276)), c.c_uint16()
                out[275] = 0xA5
                self.assertEqual(self.lib.pn532_encode(2, array(data), length, out,
                                                     275, c.byref(total)), 0)
                self.assertEqual(bytes(out)[:total.value], response(data, 0xD4, 2))
                self.assertEqual(out[275], 0xA5)

    def test_in_place_payload_does_not_get_overwritten(self):
        for length in (0, 253, 254, 262, 263):
            data = bytes(i % 251 for i in range(length))
            start = 10 if length + 2 > 255 else 7
            out, total = array(bytes(275)), c.c_uint16()
            for i, byte in enumerate(data):
                out[start + i] = byte
            ptr = c.cast(c.byref(out, start), c.POINTER(c.c_uint8))
            self.assertEqual(self.lib.pn532_encode(2, ptr, length, out, 275,
                                                 c.byref(total)), 0)
            self.assertEqual(bytes(out)[:total.value], response(data, 0xD4, 2))

    def test_capacity_and_overflow_leave_output_unchanged(self):
        for length, capacity, error in ((0, 8, 5), (263, 274, 5),
                                        (264, 275, 4), (65535, 275, 4)):
            out, total = array(bytes([0xA5]) * 275), c.c_uint16(999)
            self.assertEqual(self.lib.pn532_encode(2, array(b""), length, out,
                                                 capacity, c.byref(total)), error)
            self.assertEqual(bytes(out), bytes([0xA5]) * 275)
            self.assertEqual(total.value, 999)

    def test_truncations_and_uart_trailing_bytes(self):
        for frame in (response(b"abc"), response(bytes(263))):
            for cut in range(len(frame)):
                with self.subTest(size=len(frame), cut=cut):
                    self.assertEqual(self.decode(frame[:cut])[0], 1)
            self.assertEqual(self.decode(frame + b"\0")[0], 11)

    def test_corrupt_fields_and_wrong_direction_command(self):
        frame = response(b"abcd")
        for index, error in ((0, 2), (2, 2), (4, 3), (7, 6), (len(frame) - 1, 7)):
            corrupt = bytearray(frame)
            corrupt[index] ^= 1
            self.assertEqual(self.decode(bytes(corrupt))[0], error)
        self.assertEqual(self.decode(response(b"", 0xD4))[0], 8)
        self.assertEqual(self.decode(response(b"", command=5))[0], 9)
        self.assertEqual(self.decode(bytes.fromhex("0000ff01ff7f8100"))[0], 10)

    def test_ack_nack_prefix_and_response_rejection(self):
        for frame in (bytes.fromhex("0000ff00ff00"), bytes.fromhex("0000ffff0000")):
            total = c.c_uint16()
            self.assertEqual(self.lib.pn532_frame_length(array(frame[:5]), 5,
                                                        c.byref(total)), 0)
            self.assertEqual(total.value, 6)
            self.assertEqual(self.decode(frame)[0], 2)

    def test_extended_length_checksum_and_limit(self):
        for prefix, error in (("0000ffffff010af5", 4),
                               ("0000ffffff0109f5", 3),
                               ("0000ffffff000000", 2)):
            total = c.c_uint16()
            data = bytes.fromhex(prefix)
            self.assertEqual(self.lib.pn532_frame_length(array(data), len(data),
                                                        c.byref(total)), error)


if __name__ == "__main__":
    unittest.main()
