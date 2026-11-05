# SPDX-License-Identifier: Apache-2.0
"""Isolated FeliCa polling parser: synthetic inputs only, no hardware."""
import pathlib
import subprocess
import tempfile
import unittest


class ExperimentalFelicaTest(unittest.TestCase):
    def test_poll_and_pcsc_get_data(self):
        source = pathlib.Path(__file__).resolve().parents[1] / 'experimental/felica'
        with tempfile.TemporaryDirectory() as directory:
            program = pathlib.Path(directory) / 'test-felica'
            subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                            '-fsanitize=address,undefined', '-fno-omit-frame-pointer',
                            str(source / 'poll.c'), str(source / 'test_poll.c'),
                            '-o', str(program)], check=True)
            subprocess.run([str(program)], check=True)
