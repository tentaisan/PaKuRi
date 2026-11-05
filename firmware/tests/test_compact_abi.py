# SPDX-License-Identifier: Apache-2.0
"""省容量ABIを同じ実C/UBSanの最大境界・交差・負例へ通す。"""
import ctypes as c
import unittest
import test_card as card
import test_pn532_frame as frame
import test_isodep_b as block
import test_soft_b_reader as soft
import test_reader as reader

FLAGS=('-DMG_SINGLETON','-DMG_SOFT_B','-DMG_COMPACT_ABI')

class CompactCardTests(card.CardTests):
    extra_flags=FLAGS

class CompactFrameTests(frame.Pn532FrameTests):
    extra_flags=FLAGS

class CompactBlockTests(block.SingletonBlockTests):
    extra_flags=FLAGS

class CompactReaderTests(soft.SoftwareReaderTests):
    abi_flags=('-DMG_COMPACT_ABI',)

    def test_foreign_and_null_instances_leave_reader_and_shadow_untouched(self):
        f,s=self.prepare();snapshot=bytes(f.r),bytes(s)
        foreign=reader.Reader()
        for pointer in (c.byref(foreign),c.POINTER(reader.Reader)()):
            f.lib.reader_init(pointer,f.now);f.lib.reader_recover(pointer,f.now)
            f.lib.reader_poll(pointer,f.now);f.lib.reader_release(pointer)
            self.assertEqual(f.lib.reader_scan(pointer,3,1,f.now),4)
            self.assertEqual(f.lib.reader_presence(pointer,f.now),4)
            self.assertEqual(f.lib.reader_field_off(pointer,f.now),4)
            self.assertEqual(f.lib.reader_exchange(pointer,None,261,f.now),4)
            self.assertEqual((bytes(f.r),bytes(s)),snapshot)

class CompactGateTests(soft.SoftwareGateTests):
    abi_flags=('-DMG_COMPACT_ABI',)

    def test_foreign_transport_and_tx_reject_before_touching_null_buffers(self):
        f,s=self.prepare();snapshot=bytes(f.r),bytes(f.g),bytes(s)
        other=reader.Reader();tx=type(f.g.tx)()
        for pn in (c.byref(other.pn),c.POINTER(type(other.pn))()):
            f.lib.pn_transport_init(pn);f.lib.pn_transport_poll(pn,f.now)
            f.lib.pn_transport_recover(pn,f.now);f.lib.pn_transport_release(pn)
            self.assertEqual(f.lib.pn_transport_begin(pn,0x42,None,261,263,f.now,1000),39)
        for pointer in (c.byref(tx),c.POINTER(type(tx))()):
            f.lib.ccid_tx_stop(pointer,None)
            self.assertEqual(f.lib.ccid_tx_init(pointer,268,None),0)
            self.assertEqual(f.lib.ccid_tx_push(pointer,None,64,None),0)
            self.assertEqual(f.lib.ccid_tx_delivered(pointer,None),0)
        self.assertEqual((bytes(f.r),bytes(f.g),bytes(s)),snapshot)

class CompactProfileTests(unittest.TestCase):
    def test_conflicting_profiles_or_output_directories_are_rejected(self):
        import subprocess
        from pathlib import Path
        root=Path(__file__).resolve().parents[1]
        for compact,soft_b,out in ((2,1,'wrong-soft-b'),(1,0,'wrong-compact-soft-b'),
                                  (1,1,'wrong-soft-b'),(0,1,'wrong-compact-soft-b')):
            result=subprocess.run(['make','-C',str(root),'-n',f'COMPACT={compact}',
                                   f'SOFT_B={soft_b}',f'OUT=/tmp/{out}','runtime'],
                                  text=True,capture_output=True)
            self.assertNotEqual(result.returncode,0)
