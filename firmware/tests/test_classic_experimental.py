# SPDX-License-Identifier: Apache-2.0
"""Host-only isolated Classic 1K experiment; never accesses hardware."""
import pathlib
import subprocess
import tempfile
import unittest


class ExperimentalClassicTest(unittest.TestCase):
    def test_protocol_core(self):
        source = pathlib.Path(__file__).resolve().parents[1] / 'experimental/mifare'
        with tempfile.TemporaryDirectory() as directory:
            program = pathlib.Path(directory) / 'test-classic'
            subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                            '-fsanitize=address,undefined', '-fno-omit-frame-pointer',
                            str(source / 'classic.c'), str(source / 'test_classic.c'),
                            '-o', str(program)], check=True)
            subprocess.run([str(program)], check=True)

    def test_4k_sector_boundaries_and_write_protection(self):
        source = pathlib.Path(__file__).resolve().parents[1] / 'experimental/mifare'
        with tempfile.TemporaryDirectory() as directory:
            program = pathlib.Path(directory) / 'test-classic-4k'
            subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror',
                            '-fsanitize=undefined','-DMG_CLASSIC_4K',
                            str(source/'classic.c'),str(source/'test_classic_4k.c'),
                            '-o',str(program)],check=True)
            subprocess.run([str(program)],check=True)
