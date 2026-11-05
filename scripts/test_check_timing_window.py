# SPDX-License-Identifier: Apache-2.0
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import check_timing_window as t

ASM='''.area CSEG
_timing_poll:
mov c,_EA
mov _timing_poll_enabled_1_1,c
clr _EA
mov r7,_TL0
clr _TR2
jnb _TF2,00101$
mov (_timing_poll_elapsed_1_1+0),#0xff
mov (_timing_poll_elapsed_1_1+1),#0xff
sjmp 00102$
00101$:
mov _timing_poll_elapsed_1_1,_TL2
mov (_timing_poll_elapsed_1_1+1),_TH2
00102$:
clr _TF2
mov _TL2,#0
mov _TH2,#0
setb _TR2
mov a,_TL0
clr c
subb a,r7
mov r7,a
mov c,_timing_poll_enabled_1_1
mov _EA,c
ret
'''


class TimingWindowTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='pakuri-timing-window-')
        self.addCleanup(self.tmp.cleanup)
        self.asm=Path(self.tmp.name)/'timing.asm'
        self.asm.write_text(ASM)

    def test_all_paths_bound_both_windows(self):
        result=t.analyze(self.asm)
        self.assertEqual(result['read_window_instructions'],11)
        self.assertEqual(result['interrupt_mask_instructions'],17)
        self.assertEqual(result['read_window_ticks_model_bound'],44)
        self.assertFalse(result['exact_ch552_instruction_cycles_verified'])

    def reject(self,text):
        self.asm.write_text(text)
        with self.assertRaises((t.TimingWindowError,ValueError)):t.analyze(self.asm)

    def test_loops_calls_and_indirect_memory_rejected(self):
        self.reject(ASM.replace('sjmp 00102$','sjmp 00101$').replace('mov _timing_poll_elapsed_1_1,_TL2','sjmp 00101$'))
        self.reject(ASM.replace('clr _TF2','lcall _foreign'))
        self.reject(ASM.replace('clr _TF2','mov a,@r0'))

    def test_unqualified_sfr_and_interrupt_writes_rejected(self):
        self.reject(ASM.replace('clr _TF2','mov _CLOCK_CFG,#0'))
        self.reject(ASM.replace('clr _TF2','setb _EA'))
        self.reject(ASM.replace('mov a,_TL0','mov a,_TH0'))

    def test_slow_forward_window_rejected(self):
        self.reject(ASM.replace('clr _TF2','mov r0,r0\n'*64+'clr _TF2'))

    def test_bundle_hashes_are_bound_to_assembly(self):
        image=self.asm.with_suffix('.bin');image.write_bytes(bytes(14336))
        report=self.asm.with_suffix('.stack.json')
        report.write_text(json.dumps({'image_padded_sha256':hashlib.sha256(image.read_bytes()).hexdigest(),
                                     'assembly_sha256':{'timing.asm':hashlib.sha256(self.asm.read_bytes()).hexdigest()}}))
        result=t.qualify(self.asm,image,report)
        self.assertEqual(result['image_sha256'],hashlib.sha256(image.read_bytes()).hexdigest())
        self.asm.write_text(ASM+';changed\n')
        with self.assertRaises(t.TimingWindowError):t.qualify(self.asm,image,report)


if __name__=='__main__':unittest.main()
