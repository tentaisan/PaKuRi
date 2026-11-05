# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
import subprocess
import tempfile
import unittest
import test_gate as gate


class TimingGateTests(gate.GateTests):
    """Same actual-C transaction/cancellation matrix in the measurement build."""
    timing_mode=True


class TimingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='pakuri-timing-')
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.exe=Path(cls.tmp.name)/'timing-test'
        source=Path(__file__).with_name('timing_harness.c')
        subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=undefined',
                        '-fno-sanitize-recover=all',str(source),'-o',str(cls.exe)],check=True)

    def test_initialization_preserves_uart_and_timer01(self):
        subprocess.run([str(self.exe),'init'],check=True)

    def test_poll_restores_interrupt_state_and_saturates_overflow(self):
        subprocess.run([str(self.exe),'poll'],check=True)

    def test_irq_lateness_monotone_and_saturating(self):
        subprocess.run([str(self.exe),'irq'],check=True)

    def test_uart_overflow_survives_transport_recovery(self):
        subprocess.run([str(self.exe),'uart'],check=True)

    def test_fixed_read_only_api_and_old_snapshot_rejection(self):
        subprocess.run([str(self.exe),'usb'],check=True)

    def test_build_output_separation(self):
        firmware=Path(__file__).resolve().parents[1]
        for options in (['TIMING=2'],['TIMING=1','OUT=/tmp/pakuri-normal'],
                        ['TIMING=0','OUT=/tmp/pakuri-timing']):
            result=subprocess.run(['make','-s','-n','runtime',*options],cwd=firmware,capture_output=True)
            self.assertNotEqual(result.returncode,0)


if __name__=='__main__':unittest.main()
