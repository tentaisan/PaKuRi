# SPDX-License-Identifier: Apache-2.0
import tempfile
import unittest
from pathlib import Path
from intelhex import IntelHex
import check_ch559_candidate as check


class CandidateImageTests(unittest.TestCase):
    def test_boundaries_and_reset_vector(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'candidate.hex'
            image = IntelHex(); image[0]=2; image[1]=0; image[2]=3; image[3]=0
            image[check.APP_SIZE-1]=42; image.write_hex_file(str(path))
            report, data = check.checked_image(path)
            self.assertEqual((len(data), report['highest_address']), (check.APP_SIZE, check.APP_SIZE-1))
            self.assertFalse(report['flash_authorized'])
            image[check.APP_SIZE]=0; image.write_hex_file(str(path))
            with self.assertRaises(ValueError): check.checked_image(path)
            del image[check.APP_SIZE]; image[0]=0; image.write_hex_file(str(path))
            with self.assertRaises(ValueError): check.checked_image(path)
