# SPDX-License-Identifier: Apache-2.0
"""新Type B block engineの合成RF試験。実カード/USB/UARTは使わない。"""
import ctypes as c
from pathlib import Path
import subprocess
import tempfile
import unittest


class State(c.Structure):
    _fields_=[('buffer',c.c_uint8*261)]+[(n,c.c_uint16) for n in ('length','offset','used')]+[
        (n,c.c_uint8) for n in ('limit','block','cid','header','phase','resume','wtx','wtx_left')]


class BlockTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.tmp.cleanup)
        source=Path(__file__).resolve().parents[1]/'src/isodep_b.c'
        out=Path(cls.tmp.name)/'depb.so'
        subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-shared','-fPIC',
                        '-fsanitize=undefined','-fno-sanitize-recover=all',*(['-DMG_SINGLETON'] if getattr(cls,'singleton',False) else []),*getattr(cls,'extra_flags',()),str(source),*([str(source.parents[1]/'tests/compact_abi_exports.c'),'-DMG_ABI_BLOCK_ONLY'] if '-DMG_COMPACT_ABI' in getattr(cls,'extra_flags',()) else []),'-o',str(out)],check=True)
        cls.lib=c.CDLL(str(out));cls.lib.depb_clear.argtypes=[c.POINTER(State)]
        cls.lib.depb_begin.argtypes=[c.POINTER(State),c.POINTER(c.c_uint8),c.c_uint16,c.c_uint8,c.c_uint8]
        cls.lib.depb_next.argtypes=[c.POINTER(State),c.POINTER(c.c_uint8)];cls.lib.depb_next.restype=c.c_uint16
        cls.lib.depb_receive.argtypes=[c.POINTER(State),c.POINTER(c.c_uint8),c.c_uint16]

    def start(self,fsci=8,cid=1,length=261):
        self.s=State.in_dll(self.lib,'depb_state') if getattr(self,'singleton',False) else State()
        self.lib.depb_clear(c.byref(self.s));self.request=bytes((i*37+11)&255 for i in range(length))
        self.assertEqual(self.lib.depb_begin(c.byref(self.s),(c.c_uint8*length).from_buffer_copy(self.request),length,fsci,cid),0)

    def next(self):
        out=(c.c_uint8*256)(*([0xa5]*256));size=self.lib.depb_next(c.byref(self.s),out)
        self.assertLessEqual(size,254);self.assertEqual(bytes(out[254:]),b'\xa5\xa5')
        return bytes(out[:size])

    def receive(self,data):
        return self.lib.depb_receive(c.byref(self.s),(c.c_uint8*len(data)).from_buffer_copy(data),len(data))

    def header(self,pcb):
        return bytes((pcb|8,self.s.cid)) if self.s.cid else bytes((pcb,))

    def send_request(self):
        reconstructed=bytearray()
        while True:
            block=self.next();reconstructed+=block[self.s.header:]
            if not block[0]&0x10:break
            self.assertEqual(self.receive(self.header(0xa2|(block[0]&1))),0)
        self.assertEqual(bytes(reconstructed),self.request)

    def test_all_frame_sizes_cids_preserve_maximum_request_and_chained_response(self):
        data=bytes(range(256))+b'\x90\0'
        for fsci in range(9):
            for cid in (0,1,14):
                with self.subTest(fsci=fsci,cid=cid):
                    self.start(fsci,cid);self.send_request()
                    for offset in range(0,len(data),60):
                        chunk=data[offset:offset+60];more=offset+len(chunk)<len(data)
                        self.assertEqual(self.receive(self.header(0x02|self.s.block|(0x10 if more else 0))+chunk),0)
                        if more:self.assertEqual(self.next(),self.header(0xa2|self.s.block))
                    self.assertEqual(self.s.phase,6);self.assertEqual(self.s.used,258)
                    self.assertEqual(bytes(self.s.buffer[:258]),data)

    def test_wtx_during_command_and_response_keeps_block_and_does_not_replay_apdu(self):
        self.start(fsci=0)
        first=self.next();old_offset=self.s.offset
        for _ in range(16):
            wtx=self.header(0xf2)+b'\x02'
            self.assertEqual(self.receive(wtx),0);self.assertEqual(self.next(),wtx)
            self.assertEqual(self.s.offset,old_offset);self.assertEqual(self.s.block,0)
        self.assertEqual(self.receive(self.header(0xf2)+b'\x02'),1)
        self.assertEqual(self.s.phase,7);self.assertEqual(bytes(self.s.buffer),bytes(261))
        self.start(length=22);self.send_request();old_offset=self.s.offset
        wtx=self.header(0xf2)+b'\x3b';self.assertEqual(self.receive(wtx),0)
        self.assertEqual(self.next(),wtx);self.assertEqual(self.s.offset,old_offset)
        self.assertEqual(self.receive(self.header(2|self.s.block)+b'\x6a\x82'),0)
        self.assertEqual(bytes(self.s.buffer[:self.s.used]),b'\x6a\x82')

    def test_literal_pcd_chaining_acknowledges_sent_number_before_toggle(self):

        self.start(fsci=0,cid=1,length=261)
        self.assertEqual(self.next()[:2],b'\x1a\x01')
        self.assertEqual(self.receive(b'\xaa\x01'),0)
        self.assertEqual(self.s.block,1)
        self.assertEqual(self.next()[:2],b'\x1b\x01')
        self.assertEqual(self.receive(b'\xab\x01'),0)
        self.assertEqual(self.s.block,0)
        self.assertEqual(self.next()[:2],b'\x1a\x01')
        self.assertEqual(self.receive(b'\xab\x01'),1)
        self.assertEqual(bytes(self.s.buffer),bytes(261))

    def test_bad_frame_cid_block_ack_wtx_and_overflow_fail_closed(self):
        for data in (b'',b'\x0a',b'\x0a\x02\x90\0',b'\x0b\x01\x90\0',
                     b'\x0e\x01\x90\0',b'\x02\x90\0',b'\xba\x01',
                     b'\x0a\x01',b'\xfa\x01\0',b'\xfa\x01\x3c',b'\xfa\x01\x02\0',
                     b'\x0a\x01'+bytes(61)):
            with self.subTest(data=data):
                self.start(length=22);self.send_request();self.assertEqual(self.receive(data),1)
                self.assertEqual(self.s.phase,7);self.assertEqual(bytes(self.s.buffer),bytes(261))
        self.start(fsci=0);self.next()
        self.assertEqual(self.receive(self.header(0xa3)),1)
        self.start(length=22);self.send_request()
        for _ in range(4):
            self.assertEqual(self.receive(self.header(0x12|self.s.block)+bytes(60)),0);self.next()
        self.assertEqual(self.receive(self.header(2|self.s.block)+bytes(19)),1)
        self.assertEqual(self.s.phase,7)

    def test_clear_and_invalid_begin_never_leave_old_data_usable(self):
        self.start();self.lib.depb_clear(c.byref(self.s))
        self.assertEqual(self.s.phase,0);self.assertEqual(bytes(self.s.buffer),bytes(261))
        for length,fsci,cid in ((3,8,1),(262,8,1),(22,9,1),(22,8,15)):
            self.lib.depb_clear(c.byref(self.s))
            self.assertEqual(self.lib.depb_begin(c.byref(self.s),(c.c_uint8*262)(),length,fsci,cid),1)
            self.assertEqual(self.s.phase,7)


class SingletonBlockTests(BlockTests):
    singleton=True

    def test_other_instance_is_rejected_without_touching_active_state(self):
        self.start();before=bytes(self.s);other=State();out=(c.c_uint8*256)()
        self.lib.depb_clear(c.byref(other))
        self.assertEqual(self.lib.depb_begin(c.byref(other),out,22,8,1),1)
        self.assertEqual(self.lib.depb_next(c.byref(other),out),0)
        self.assertEqual(self.lib.depb_receive(c.byref(other),out,2),1)
        self.assertEqual(bytes(self.s),before)
