# SPDX-License-Identifier: Apache-2.0
"""Synthetic FeliCa read-only PC/SC conversion; no hardware."""
import pathlib
import subprocess
import tempfile
import unittest


class ExperimentalFelicaReadTest(unittest.TestCase):
    def test_read_protocol_core(self):
        source=pathlib.Path(__file__).resolve().parents[1]/'experimental/felica'
        with tempfile.TemporaryDirectory() as directory:
            program=pathlib.Path(directory)/'test-felica-read'
            subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror',
                            '-fsanitize=address,undefined','-fno-omit-frame-pointer',
                            str(source/'read.c'),str(source/'test_read.c'),'-o',str(program)],check=True)
            subprocess.run([str(program)],check=True)
