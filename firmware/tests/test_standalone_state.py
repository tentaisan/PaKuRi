# SPDX-License-Identifier: Apache-2.0
"""Device-independent state changes; no card, GPIO, or USB hardware."""
import ctypes as c
from pathlib import Path
import subprocess
import tempfile
import unittest

class State(c.Structure):
    _fields_ = [('reader',c.c_uint8),('card_present',c.c_uint8),('host_connected',c.c_uint8)]

class StandaloneStateTests(unittest.TestCase):
    def test_transitions_and_invalid_sample(self):
        source=Path(__file__).resolve().parents[1]/'experimental/standalone/state.c'
        with tempfile.TemporaryDirectory() as d:
            so=Path(d)/'state.so'
            subprocess.run(['cc','-shared','-fPIC','-std=c11','-Wall','-Wextra','-Werror',
                            '-fsanitize=undefined',str(source),'-o',str(so)],check=True)
            lib=c.CDLL(str(so));update=lib.mg_standalone_update
            update.argtypes=[c.POINTER(State),c.POINTER(State)];update.restype=c.c_uint8
            state=State(0,0,0)
            for sample, expected in [(State(1,0,0),1),(State(1,1,0),2),
                                     (State(1,1,1),4),(State(2,0,1),3),
                                     (State(2,0,1),0)]:
                self.assertEqual(update(c.byref(state),c.byref(sample)),expected)
            invalid=State(9,1,0)
            self.assertEqual(update(c.byref(state),c.byref(invalid)),0)
            self.assertEqual((state.reader,state.card_present,state.host_connected),(2,0,1))
