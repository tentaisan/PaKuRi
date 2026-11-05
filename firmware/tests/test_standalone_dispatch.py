# SPDX-License-Identifier: Apache-2.0
"""Synthetic foreground dispatch; no output devices or card data."""
from pathlib import Path
import subprocess
import tempfile
import unittest

class DispatchTests(unittest.TestCase):
    def test_shared_snapshot_and_reentrancy(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / 'dispatch'
            subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                            '-fsanitize=undefined', '-fno-sanitize-recover=all', '-DMG_EVENTS',
                            '-DMG_DISPATCH_CONSUMER_1=first', '-DMG_DISPATCH_CONSUMER_2=second',
                            str(root/'experimental/standalone/dispatch.c'),
                            str(root/'src/events.c'), str(root/'tests/test_dispatch.c'),
                            '-o', str(binary)], check=True)
            subprocess.run([str(binary)], check=True)

    def test_no_consumers_preserves_events(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / 'dispatch-empty'
            subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                            '-DMG_EVENTS',
                            str(root/'experimental/standalone/dispatch.c'),
                            str(root/'src/events.c'), str(root/'tests/test_dispatch_no_consumers.c'),
                            '-o', str(binary)], check=True)
            subprocess.run([str(binary)], check=True)
