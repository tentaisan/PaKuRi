# SPDX-License-Identifier: AGPL-3.0-only
"""UART実装とmock SFRによる割込み・所有権・overflowの試験。"""
from pathlib import Path
import subprocess
import tempfile
import unittest


class UartTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="pakuri-uart-")
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.exe = Path(cls.tmp.name) / "uart-test"
        source = Path(__file__).with_name("uart_harness.c")
        subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                        "-fsanitize=undefined", "-fno-sanitize-recover=all",
                        *getattr(cls, 'extra_flags', ()),
                        str(source), "-o", str(cls.exe)], check=True)

    def test_clock_and_pin_initialization(self):
        subprocess.run([str(self.exe), "init"], check=True)

    def test_rx_fifo_and_wrap(self):
        subprocess.run([str(self.exe), "rx"], check=True)

    def test_overflow_latches_until_explicit_reset(self):
        subprocess.run([str(self.exe), "overflow"], check=True)

    def test_tx_completion_and_stop(self):
        subprocess.run([str(self.exe), "tx"], check=True)
