# SPDX-License-Identifier: AGPL-3.0-only
"""実機書込み前の構造検査に対する境界・破損の負例試験。"""

import tempfile
import unittest
from pathlib import Path

from intelhex import IntelHex, IntelHexError

from check_firmware_image import APP_SIZE, inspect_image, write_image
import hashlib
import json


class ImageCheckTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "test.ihx"

    def write_image(self, values):
        IntelHex(values).write_hex_file(str(self.path))

    def test_last_app_byte_is_allowed(self):
        self.write_image({0: 2, 1: 0, 2: 3, 3: 0x80, 4: 0xFE, APP_SIZE - 1: 0})
        result = inspect_image(self.path)
        self.assertEqual(result["highest_address"], APP_SIZE - 1)
        self.assertEqual(result["reset_target"], 3)
        self.assertEqual(len(result["padded_app_sha256"]), 64)

    def test_protected_addresses_are_rejected(self):
        for address in (APP_SIZE, 0x3FFF, 0xF000, 0x10000):
            with self.subTest(address=address):
                self.write_image({0: 2, 1: 0, 2: 3, 3: 0x80, address: 0})
                with self.assertRaisesRegex(ValueError, "outside app range"):
                    inspect_image(self.path)

    def test_invalid_vectors_are_rejected(self):
        for values in ({}, {0: 2}, {0: 0, 1: 0, 2: 3, 3: 0},
                       {0: 2, 1: 0, 2: 0}, {0: 2, 1: 0, 2: 3},
                       {0: 2, 1: 0x38, 2: 0}, {0: 2, 1: 0, 2: 3, 3: 0xFF}):
            with self.subTest(values=values):
                self.write_image(values)
                with self.assertRaises(ValueError):
                    inspect_image(self.path)

    def test_bad_checksum_is_rejected(self):
        self.path.write_text(":03000000020003F9\n:00000001FF\n")
        with self.assertRaises(IntelHexError):
            inspect_image(self.path)

    def test_overlap_is_rejected(self):
        self.path.write_text(":03000000020003F8\n:03000000020003F8\n:00000001FF\n")
        with self.assertRaises(IntelHexError):
            inspect_image(self.path)

    def test_start_address_record_is_rejected(self):
        image = IntelHex({0: 2, 1: 0, 2: 3, 3: 0x80})
        image.start_addr = {"EIP": 3}
        image.write_hex_file(str(self.path))
        with self.assertRaisesRegex(ValueError, "start-address"):
            inspect_image(self.path)

    def test_binary_contains_only_padded_application_region(self):
        self.write_image({0: 2, 1: 0, 2: 3, 3: 0x80})
        output = self.path.with_suffix(".bin")
        report = write_image(self.path, output)
        binary = output.read_bytes()
        self.assertEqual(len(binary), APP_SIZE)
        self.assertEqual(binary[:4], bytes([2, 0, 3, 0x80]))
        self.assertEqual(binary[4:], bytes([255]) * (APP_SIZE - 4))
        self.assertEqual(hashlib.sha256(binary).hexdigest(), report["padded_app_sha256"])
        self.assertFalse(json.loads(output.with_suffix(".json").read_text())["flash_authorized"])

    def test_bad_image_does_not_create_binary_or_report(self):
        self.write_image({APP_SIZE: 0})
        output = self.path.with_suffix(".bin")
        with self.assertRaises(ValueError):
            write_image(self.path, output)
        self.assertFalse(output.exists())
        self.assertFalse(output.with_suffix(".json").exists())

    def test_output_collision_does_not_overwrite_input(self):
        self.write_image({0: 2, 1: 0, 2: 3, 3: 0x80})
        before = self.path.read_bytes()
        with self.assertRaises(ValueError):
            write_image(self.path, self.path)
        self.assertEqual(self.path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
