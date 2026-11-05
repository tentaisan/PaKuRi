# SPDX-License-Identifier: Apache-2.0
import ctypes as c
import unittest
import test_reader as reader
import test_gate as gate
from test_isodep_b import State


class SoftwareReaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture=type('SoftwareFixture',(reader.ReaderTests,),{'singleton':True,'extra_flags':('-DMG_SOFT_B',*getattr(cls,'abi_flags',()))})
        cls.fixture.setUpClass();cls.addClassCleanup(cls.fixture.doClassCleanups)

    def prepare(self):
        f=self.fixture();f.setUp()
        for payload in (reader.VERSION,b'',b'',b'',b''):f.respond(payload)
        self.assertEqual(f.r.initialized,1);f.release();f.scan(3);f.release()
        return f,State.in_dll(f.lib,'depb_state')

    def sent_payload(self,f):
        frame=f.r.pn.frame
        start=10 if bytes(frame[3:5])==b'\xff\xff' else 7
        return bytes(frame[start:f.r.pn.total-2])

    def test_261_request_wtx_and_258_chained_response_preserve_one_deadline(self):
        f,s=self.prepare();before=len(f.sent())
        request=bytes((0,0xa4,4,0,255))+bytes(range(256))
        self.assertEqual(f.exchange(request),0);deadline=f.r.pn.deadline
        self.assertEqual(self.sent_payload(f),b'\x1a\x01'+request[:252])
        f.respond(b'\0\xaa\x01')
        self.assertEqual(self.sent_payload(f),b'\x0b\x01'+request[252:])
        self.assertEqual(f.r.pn.deadline,deadline)
        f.respond(b'\0\xfa\x01\x02')
        self.assertEqual(self.sent_payload(f),b'\xfa\x01\x02')
        self.assertEqual(f.r.pn.deadline,deadline)
        data=bytes(range(256))+b'\x90\0'
        for offset in range(0,258,60):
            more=offset+60<258
            pcb=0x0a|s.block|(0x10 if more else 0)
            f.respond(bytes((0,pcb,1))+data[offset:offset+60])
            if more:
                self.assertEqual(self.sent_payload(f),bytes((0xaa|s.block,1)))
                self.assertEqual(f.r.pn.deadline,deadline)
        self.assertEqual(f.r.phase,reader.R_DONE)
        self.assertEqual(bytes(f.r.pn.frame[f.r.pn.offset:f.r.pn.offset+f.r.pn.payload]),data)
        self.assertEqual(f.sent()[before:].count(request[:32]),1)
        f.release();self.assertEqual(bytes(s.buffer),bytes(261))

    def test_block_number_survives_reply_release_and_presence_without_replay(self):
        f,s=self.prepare();request=bytes.fromhex('00a4040000')
        self.assertEqual(f.exchange(request),0);f.respond(b'\0\x0a\x01\x6a\x82');f.release()
        self.assertEqual(f.r.activate,1)
        f.lib.reader_presence(c.byref(f.r),f.now)
        self.assertEqual(self.sent_payload(f),b'\xbb\x01')
        f.respond(b'\0\xab\x01');f.release()
        self.assertEqual(f.exchange(request),0)
        self.assertEqual(self.sent_payload(f),b'\x0b\x01'+request)
        f.respond(b'\0\x0b\x01\x90\0');f.release()
        self.assertEqual(f.r.activate,0)

    def test_timeout_wrap_or_wrong_cid_wipes_shadow_and_invalidates_connection(self):
        for wrong in (False,True):
            f,s=self.prepare();f.now=65000
            self.assertEqual(f.exchange(bytes.fromhex('00a4040000')),0)
            deadline=f.r.pn.deadline
            if wrong:f.respond(b'\0\x0a\x02\x90\0')
            else:
                f.respond(b'\0\xfa\x01\x02');self.assertEqual(f.r.pn.deadline,deadline)
                f.now=(deadline-1)&65535;f.poll()
            self.assertEqual(f.r.phase,reader.R_FAILED)
            self.assertEqual((f.r.active,f.r.selected,f.r.initialized),(0,0,0))
            self.assertEqual(bytes(s.buffer),bytes(261))


class SoftwareGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture=type('SoftwareGateFixture',(gate.GateTests,),{'extra_flags':('-DMG_SOFT_B',*getattr(cls,'abi_flags',()))})
        cls.fixture.setUpClass();cls.addClassCleanup(cls.fixture.doClassCleanups)

    def prepare(self):
        f=self.fixture();f.setUp()
        for payload in (gate.VERSION,b'',b'',b'',b''):f.respond(payload)
        f.power_on(3);return f,State.in_dll(f.lib,'depb_state')

    def test_presence_deadline_recovers_without_apdu_and_discovers_replacement(self):
        f,s=self.prepare();f.notifications();f.poll(200)
        self.assertEqual((f.g.background,f.r.phase),(2,8))
        f.poll(1100)
        self.assertEqual((f.g.background,f.r.phase,f.r.present,f.g.powered),(0,1,0,0))
        self.assertEqual(bytes(s.buffer),bytes(261))
        self.assertEqual(f.g.startup_retry,0)
        for payload in (gate.VERSION,b'',b'',b'',b''):f.respond(payload)
        f.notifications();f.poll(200)
        self.assertEqual(f.r.pn.command,0x4a)
        f.respond(gate.type_a())
        self.assertEqual((f.r.card.type,f.r.present,f.r.active,f.g.powered),(0,1,0,0))
        self.assertEqual(f.g.active,0)

    def test_application_deadline_is_not_replayed_by_presence_recovery(self):
        f,s=self.prepare()
        f.send(gate.command(0x6f,bytes.fromhex('00a4040000')))
        f.poll(15001)
        self.assertEqual(f.r.phase,reader.R_FAILED)
        self.assertEqual(bytes(s.buffer),bytes(261))
        f.final();f.notifications();f.poll(200)
        self.assertEqual(f.r.phase,reader.R_FAILED)

    def test_abort_and_usb_reset_wipe_partial_b_request_and_allow_fresh_a(self):
        for reset in (False,True):
            f,s=self.prepare()
            f.send(gate.command(0x6f,bytes((0,0xa4,4,0,255))+bytes(256),sequence=41))
            f.respond(b'\0\xaa\x01')
            self.assertNotEqual(bytes(s.buffer),bytes(261))
            if reset:
                f.lib.test_reset();f.poll();f.setup(0,9,1);f.transfer(0x20,0)
            else:f.abort(41)
            self.assertEqual(bytes(s.buffer),bytes(261))
            for payload in (gate.VERSION,b'',b'',b'',b''):f.respond(payload)
            if not reset:f.final()
            f.power_on(0)
            f.send(gate.command(0x6f,bytes.fromhex('00a4040000')))
            f.respond(b'\0\x90\0');message,_=f.final()
            self.assertEqual(message[10:],b'\x90\0')

    def test_chained_b_response_and_wtx_keep_ccid_sequence_and_five_packet_reply(self):
        f,s=self.prepare()
        f.send(gate.command(0x6f,bytes((0,0xa4,4,0,255))+bytes(range(256)),sequence=89))
        deadline=f.g.deadline
        f.respond(b'\0\xaa\x01');f.respond(b'\0\xfa\x01\x02')
        f.poll(300);extension,_=f.collect()
        self.assertEqual(extension[6:10],bytes((89,0x80,1,0)))
        self.assertEqual((f.g.deadline,f.r.pn.deadline),(deadline,deadline))
        data=bytes(range(256))+b'\x90\0'
        for offset in range(0,258,60):
            more=offset+60<258
            f.respond(bytes((0,0x0a|s.block|(0x10 if more else 0),1))+data[offset:offset+60])
        message,sizes=f.final()
        self.assertEqual(message[6:10],bytes((89,0,0,0)))
        self.assertEqual(message[10:],data);self.assertEqual(sizes,[64,64,64,64,12])
        self.assertEqual(bytes(s.buffer),bytes(261))
