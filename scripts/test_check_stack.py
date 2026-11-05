# SPDX-License-Identifier: AGPL-3.0-only
"""stack検査器の負例。未知命令/再帰/壊れたframeを成功扱いしない。"""
from pathlib import Path
import tempfile
import unittest

from check_stack import analyze, StackError


INTERRUPTS = """
_serial_interrupt:
    push acc
    pop acc
    reti
_timer0_interrupt:
    push acc
    push psw
    pop psw
    pop acc
    reti
"""


class StackTests(unittest.TestCase):
    def test_foreground_static_abi_rejects_even_a_balanced_isr_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fixture.asm"
            code = ".area CSEG (CODE)\n_main:\nloop$:\n sjmp loop$\n_leaf:\n ret\n"
            path.write_text(code + INTERRUPTS)
            self.assertTrue(analyze([path], 128, require_leaf_interrupts=True)["leaf_interrupts_required"])
            path.write_text(code + INTERRUPTS.replace("_serial_interrupt:\n", "_serial_interrupt:\n lcall _leaf\n"))
            with self.assertRaisesRegex(StackError, "non-leaf interrupt"):
                analyze([path], 128, require_leaf_interrupts=True)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "fixture.asm"

    def check(self, code, start=128):
        self.path.write_text(".area CSEG (CODE)\n" + code + INTERRUPTS)
        return analyze([self.path], start)

    def test_nested_calls_include_arguments_locals_and_interrupt_pc(self):
        result = self.check("""
_main:
    push acc
    lcall _frame
    pop acc
loop$:
    sjmp loop$
_frame:
    push _bp
    mov a,sp
    mov _bp,a
    add a,#0x04
    mov sp,a
    lcall _leaf
    mov sp,_bp
    pop _bp
    ret
_leaf:
    push acc
    pop acc
    ret
""")
        self.assertEqual(result["foreground_bytes"], 11)
        self.assertEqual(result["conservative_nested_bound_bytes"], 18)

    def test_branch_join_and_tail_call_preserve_stack_bound(self):
        result = self.check("""
_main:
    lcall _choice
loop$:
    sjmp loop$
_choice:
    jz alternate$
    push acc
    pop acc
    sjmp done$
alternate$:
    push acc
    push b
    pop b
    pop acc
done$:
    ljmp _leaf
_leaf:
    ret
""")
        self.assertEqual(result["foreground_bytes"], 4)

    def test_accumulator_join_becomes_unknown_not_a_fake_proof(self):
        with self.assertRaisesRegex(StackError, "unknown SP assignment"):
            self.check("""
_main:
    mov a,sp
    jz join$
    inc a
join$:
    mov sp,a
loop$:
    sjmp loop$
""")

    def test_pop_does_not_forge_a_saved_base_pointer(self):
        with self.assertRaisesRegex(StackError, "unverified byte"):
            self.check("""
_main:
    push acc
    mov _bp,sp
    pop _bp
    ret
""")

    def test_bad_returns_or_live_tail_frames_are_rejected(self):
        for body in ("push acc\n ret", "mov _bp,sp\n ret", "push acc\n ljmp _leaf"):
            with self.subTest(body=body), self.assertRaises(StackError):
                self.check("_main:\n" + body + "\n_leaf:\n ret\n")

    def test_recursive_unknown_and_indirect_calls_are_rejected(self):
        for body in ("lcall _main\n ret", "lcall _missing\n ret", "jmp @a+dptr"):
            with self.subTest(body=body), self.assertRaises(StackError):
                self.check("_main:\n" + body + "\n")

    def test_unknown_stack_writes_and_growing_loop_are_rejected(self):
        for body in ("anl sp,#0x7f", "mov sp,r0", "inc _bp", "push acc\n sjmp _main"):
            with self.subTest(body=body), self.assertRaises(StackError):
                self.check("_main:\n" + body + "\n ret\n")

    def test_stack_reservation_and_ram_boundary_are_enforced(self):
        code = "_main:\n" + "push acc\n" * 123 + "pop acc\n" * 123 + "ret\n"
        with self.assertRaisesRegex(StackError, "exceeds reserved"):
            self.check(code)
        with self.assertRaisesRegex(StackError, "invalid physical"):
            self.check("_main:\n ret\n", start=200)

    def test_unexpected_interrupt_set_is_rejected(self):
        with self.assertRaisesRegex(StackError, "unexpected interrupt"):
            self.check("_main:\n ret\n_third_interrupt:\n reti\n")


if __name__ == "__main__":
    unittest.main()
