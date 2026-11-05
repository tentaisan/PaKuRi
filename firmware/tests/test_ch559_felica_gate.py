# SPDX-License-Identifier: Apache-2.0
"""Synthetic Type F discovery, PC/SC IDm and removal; no hardware."""
import ctypes as c
import unittest
import test_gate as gate
from test_card import type_a, type_b
from test_ch559_classic_gate import CandidateReader


IDM=bytes(range(1,9))
PMM=bytes(range(0x20,0x28))


class FelicaGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        class Fixture(gate.GateTests):
            extra_flags=('-DMG_SOFT_B','-DMG_COMPACT_ABI','-DMG_UID_PROFILE',
                         '-DMG_CH559','-DMG_CH559_CLASSIC','-DMG_CLASSIC_STACK_AUTO','-DMG_CH559_FELICA',
                         '-DMG_CCID_DIAGNOSTIC')
            def setUp(self):
                super().setUp();self.r=CandidateReader.in_dll(self.lib,'reader_state')
        cls.fixture=Fixture;Fixture.setUpClass();cls.addClassCleanup(Fixture.doClassCleanups)

    def initialized(self):
        f=self.fixture();f.setUp()
        for p in (gate.VERSION,b'',b'',b'',b''):f.respond(p)
        return f

    def power_f(self,f,extra=b'',idm=IDM):
        f.send(gate.command(0x62));f.respond(b'');f.respond(b'\0');f.respond(b'\0')
        f.respond(bytes([1,1,18+len(extra),1])+idm+PMM+extra)
        return f.final()[0]

    def test_felica_discovery_idm_and_removal(self):
        for system in (b'',b'\x12\xfc'):
            with self.subTest(with_system=bool(system)):
                f=self.initialized();message=self.power_f(f,system)
                self.assertEqual(message[7]&0xc0,0)
                self.assertEqual(message[10:22],bytes.fromhex('3b8f8001804f0ca000000306'))
                self.assertEqual(message[22],0x11)
                self.assertEqual(len(message[10:]),20)
                check=0
                for byte in message[11:]:check^=byte
                self.assertEqual(check,0)
                self.assertEqual((f.r.card.type,f.r.card.cid),(2,8))
                self.assertEqual(bytes(f.r.card.uid[:8]),IDM)
                self.assertIn(bytes.fromhex('d44a010100ffff0000'),f.sent())
                f.notifications();before=f.sent()
                f.send(gate.command(0x6f,bytes.fromhex('ffca000000')))
                self.assertEqual(f.final()[0][10:],IDM+bytes.fromhex('9000'))
                self.assertEqual(f.sent(),before)
                f.send(gate.command(0x6f,bytes.fromhex('ffca000006')))
                self.assertEqual(f.final()[0][10:],bytes.fromhex('6c08'))
                f.poll(200);self.assertEqual((f.g.background,f.r.pn.command),(2,0x52))
                f.respond(b'\0');self.assertEqual(f.r.pn.command,0x4a)
                f.respond(b'\0')
                self.assertEqual((f.r.present,f.r.active,f.g.powered),(0,0,0))
                self.assertEqual(bytes(f.r.card.uid),bytes(10))

    def test_felica_does_not_accept_classic_or_unknown_commands(self):
        f=self.initialized();self.power_f(f);f.notifications();before=f.sent()
        for apdu in (bytes.fromhex('ff82000006010203040506'),bytes.fromhex('ffb0000410')):
            f.send(gate.command(0x6f,apdu));message,_=f.final()
            self.assertEqual(message[7]&0xc0,0x40)
            self.assertEqual(f.sent(),before)

    def test_a_b_remain_available_without_f_scan(self):
        for kind in (0,3):
            with self.subTest(kind=kind):
                f=self.initialized();f.send(gate.command(0x62));f.respond(b'')
                if kind==3:f.respond(b'\0')
                f.respond(type_a() if kind==0 else type_b())
                self.assertEqual(f.final()[0][7]&0xc0,0)
                f.notifications();f.send(gate.command(0x6f,bytes.fromhex('00a4040000')))
                f.respond(b'\0\x90\0' if kind==0 else b'\0\x0a\x01\x90\0')
                self.assertEqual(f.final()[0][10:],bytes.fromhex('9000'))
                self.assertNotIn(bytes.fromhex('d44a010100ffff0000'),f.sent())

    def test_iso_dep_replacement_notifies_removal_before_new_detection(self):
        for old, new in ((0, 3), (3, 0)):
            with self.subTest(old=old, new=new):
                f=self.initialized();f.power_on(old);f.notifications();f.poll(200)
                self.assertEqual((f.g.background,f.r.pn.command),(2,0x42))
                f.respond(b'\x01')
                self.assertEqual((f.r.present,f.r.active,f.g.powered),(0,0,0))
                self.assertEqual(bytes(f.ep1[:2]),b'\x50\x02')
                f.notifications();f.poll(200)
                if new==3:f.respond(b'\0')
                f.respond(type_a() if new==0 else type_b())
                self.assertEqual((f.r.present,f.r.active,f.g.powered),(1,0,0))
                self.assertEqual(bytes(f.ep1[:2]),b'\x50\x03')
                f.notifications();f.power_on(new)

    def test_bad_felica_poll_response_fails_closed(self):
        good=bytes([1,1,18,1])+IDM+PMM
        for payload in (good[:-1],good+b'\0',good[:2]+b'\x11'+good[3:],
                        good[:3]+b'\x02'+good[4:],b'\x02'+good[1:]):
            with self.subTest(length=len(payload),head=payload[:4]):
                f=self.initialized();f.send(gate.command(0x62));f.respond(b'');f.respond(b'\0');f.respond(b'\0')
                f.respond(payload);message,_=f.final()
                self.assertEqual(message[7]&0xc0,0x40)
                self.assertEqual((f.r.present,f.r.active),(0,0))
                self.assertEqual(bytes(f.r.card.uid),bytes(10))

    def test_background_scans_a_then_b_then_f(self):
        f=self.initialized();f.notifications();f.poll(200)
        self.assertEqual(f.r.pn.command,0x4a)
        f.respond(b'\0');f.respond(b'\0')
        f.respond(bytes([1,1,18,1])+IDM+PMM)
        self.assertEqual((f.r.present,f.r.card.type),(1,2))
        self.assertIn(bytes.fromhex('d44a010100ffff0000'),f.sent())

    def test_ccid_diagnostic_reports_receive_lock_without_card_data(self):
        f=self.initialized();f.notifications()
        f.send(b'\x6f\x04\0');f.poll(1100)
        self.assertEqual((f.g.rx_closed,f.get('usb_accept_out')),(1,0))
        f.setup(0xc0,0x5d,length=8)
        self.assertEqual(bytes(f.ep0[:8]),bytes([f.g.job,f.g.background,1,
                         f.g.active,f.g.response,f.get('usb_out_pending'),0,0]))
        self.assertEqual(f.get('UEP0_T_LEN'),8)

        self.assertEqual(f.get('UEP2_CTRL') & 12, 8)
        f.setup(0x82, 0, index=2, length=2)
        self.assertEqual(bytes(f.ep0[:2]), b'\0\0')
        f.transfer(0x20, 0)

        f.lib.test_reset(); f.poll()
        f.setup(0, 9, 1); f.transfer(0x20, 0)
        self.assertEqual((f.g.rx_closed, f.get('usb_accept_out')), (0, 1))
        f.send(gate.command(0x65, sequence=23))
        message, _ = f.collect()
        self.assertEqual((message[0], message[6]), (0x81, 23))

    def test_usb_fault_immediately_updates_acceptance_diagnostic(self):
        f=self.initialized();f.notifications()
        self.assertEqual(f.get('usb_accept_out'),1)
        c.c_uint8.in_dll(f.lib,'usb_events').value=16
        f.poll()
        self.assertEqual((f.g.rx_closed,f.get('usb_accept_out')),(1,0))
        f.setup(0xc0,0x5d,length=8)
        self.assertEqual((f.ep0[2],f.ep0[6]),(1,0))

    def test_bus_reset_has_priority_over_simultaneous_fifo_fault(self):
        f=self.initialized();f.notifications()
        c.c_uint8.in_dll(f.lib,'USB_INT_FG').value=0x11
        f.poll()
        self.assertEqual((f.get('usb_configured'),f.g.rx_closed), (0,0))
        f.setup(0,9,1);f.transfer(0x20,0)
        self.assertEqual((f.g.rx_closed,f.get('usb_accept_out')),(0,1))
        f.send(gate.command(0x65, sequence=44))
        message,_=f.collect()
        self.assertEqual((message[0],message[6]),(0x81,44))

    def test_felica_replacement_invalidates_old_connection_and_idm(self):
        f=self.initialized();self.power_f(f);f.notifications();f.poll(200)
        self.assertEqual(f.r.pn.command,0x52);f.respond(b'\0')
        changed=bytes([IDM[0]^1])+IDM[1:]
        f.respond(bytes([1,1,18,1])+changed+PMM)
        self.assertEqual(f.r.pn.command,0x52)
        f.respond(b'\0')
        self.assertEqual((f.r.present,f.r.active,f.g.powered),(0,0,0))
        self.assertEqual(bytes(f.r.card.uid),bytes(10))
        f.send(gate.command(0x6f,bytes.fromhex('ffca000000')))
        message,_=f.final();self.assertEqual(message[7]&0xc0,0x40)
        self.assertNotIn(IDM,message)

    def test_pending_old_uid_request_fails_during_replacement_release(self):
        f=self.initialized();self.power_f(f);f.notifications();f.poll(200)
        f.respond(b'\0');changed=bytes([IDM[0]^1])+IDM[1:]
        f.respond(bytes([1,1,18,1])+changed+PMM)
        self.assertEqual(f.r.pn.command,0x52)
        f.send(gate.command(0x6f,bytes.fromhex('ffca000000')))
        f.respond(b'\0');message,_=f.final()
        self.assertEqual(message[7]&0xc0,0x40)
        self.assertNotIn(IDM,message)
        self.assertNotIn(changed,message)

    def test_replacement_can_be_discovered_as_new_card(self):
        f=self.initialized();self.power_f(f);f.notifications();f.poll(200)
        f.respond(b'\0');changed=bytes([IDM[0]^1])+IDM[1:]
        f.respond(bytes([1,1,18,1])+changed+PMM);f.respond(b'\0')
        self.assertEqual((f.r.present,f.g.powered),(0,0))
        f.notifications();f.poll(200)
        f.respond(b'\0');f.respond(b'\0');f.respond(bytes([1,1,18,1])+changed+PMM)
        self.assertEqual((f.r.present,f.r.active,f.g.powered),(1,0,0))
        self.assertEqual(bytes(f.r.card.uid[:8]),changed)
        f.notifications();message=self.power_f(f,idm=changed)
        self.assertEqual(message[7]&0xc0,0)
        self.assertEqual((f.r.active,f.g.powered),(1,1))

    def test_felica_presence_with_same_idm_keeps_connection(self):
        f=self.initialized();self.power_f(f);f.notifications();f.poll(200)
        f.respond(b'\0');f.respond(bytes([1,1,18,1])+IDM+PMM)
        self.assertEqual((f.r.present,f.r.active,f.g.powered),(1,1,1))
        before=f.sent();f.send(gate.command(0x6f,bytes.fromhex('ffca000000')))
        self.assertEqual(f.final()[0][10:],IDM+bytes.fromhex('9000'))
        self.assertEqual(f.sent(),before)

    def test_felica_presence_malformed_reply_invalidates_connection(self):
        f=self.initialized();self.power_f(f);f.notifications();f.poll(200)
        f.respond(b'\0');f.respond(bytes([1,1,18,2])+IDM+PMM)
        self.assertEqual((f.r.present,f.r.active,f.g.powered),(0,0,0))
        self.assertEqual(bytes(f.r.card.uid),bytes(10))

    def test_presence_timeout_invalidates_session_and_recovers_without_replay(self):
        f=self.initialized();self.power_f(f);f.notifications();f.poll(200)
        self.assertEqual((f.g.background,f.r.pn.command),(2,0x52))
        f.respond(b'\0');self.assertEqual(f.r.pn.command,0x4a)
        f.r.pn.phase=gate.FAILED;f.r.pn.error=33;f.poll()
        self.assertEqual((f.r.present,f.r.active,f.g.powered),(0,0,0))
        self.assertEqual(bytes(f.r.card.uid),bytes(10))
        self.assertNotEqual(f.r.phase,gate.R_FAILED)
        for payload in (gate.VERSION,b'',b'',b'',b''):f.respond(payload)
        f.notifications();f.poll(200)
        f.respond(b'\0');f.respond(b'\0');f.respond(bytes([1,1,18,1])+IDM+PMM)
        self.assertEqual((f.r.present,f.r.active,f.g.powered),(1,0,0))
        before=f.sent();f.send(gate.command(0x6f,bytes.fromhex('ffca000000')))
        message,_=f.final()
        self.assertEqual(message[7]&0xc0,0x40)
        self.assertNotIn(IDM,message)
        self.assertEqual(f.sent(),before)

    def test_pcsc_read_without_encryption_one_to_eight_blocks(self):
        for blocks in (1,2,8):
            with self.subTest(blocks=blocks):
                f=self.initialized();self.power_f(f);f.notifications();before=f.sent()
                body=bytes([1,0x0b,0,blocks])+b''.join(bytes([0x80,i]) for i in range(blocks))
                apdu=bytes([0xff,0xb0,0,0,len(body)])+body
                f.send(gate.command(0x6f,apdu))
                data=bytes(range(16*blocks))
                reply=bytes([0,13+len(data),7])+IDM+bytes([0,0,blocks])+data
                f.respond(reply);message,sizes=f.final()
                self.assertEqual(message[10:],bytes([blocks])+data+bytes.fromhex('9000'))
                expected=bytes([0xd4,0x40,1,10+len(body),6])+IDM+body
                self.assertEqual(f.sent()[len(before):].count(expected),1)
                if blocks==8:self.assertEqual(sizes,[64,64,13])

    def test_invalid_read_is_local_and_does_not_send_rf(self):
        f=self.initialized();self.power_f(f);f.notifications();before=f.sent()
        for apdu in (bytes.fromhex('ffb0000006010b00008000'),
                     bytes.fromhex('ffb0000006010b00018100'),
                     bytes.fromhex('ffb0000006020b00018000')):
            f.send(gate.command(0x6f,apdu));message,_=f.final()
            self.assertEqual(message[10:],bytes.fromhex('6a80'))
            self.assertEqual(f.sent(),before)

    def test_card_error_and_mismatched_idm_fail_without_replay(self):
        apdu=bytes.fromhex('ffb0000006010b00018000')
        for mismatch in (False,True):
            with self.subTest(mismatched_idm=mismatch):
                f=self.initialized();self.power_f(f);f.notifications();before=f.sent()
                f.send(gate.command(0x6f,apdu))
                idm=bytes([IDM[0]^1])+IDM[1:] if mismatch else IDM
                f.respond(bytes([0,12,7])+idm+bytes([1,0]));message,_=f.final()
                if mismatch:
                    self.assertEqual(message[7]&0xc0,0x40)
                    self.assertEqual((f.r.present,f.r.active),(0,0))
                    self.assertEqual(bytes(f.r.card.uid),bytes(10))
                else:self.assertEqual(message[10:],bytes.fromhex('6300'))
                self.assertEqual(f.sent()[len(before):].count(bytes.fromhex('d44001')),1)

    def test_usb_reset_during_read_invalidates_idm_without_replay(self):
        f=self.initialized();self.power_f(f);f.notifications();before=f.sent()
        f.send(gate.command(0x6f,bytes.fromhex('ffb0000006010b00018000')))
        f.poll();f.lib.test_reset();f.poll()
        self.assertEqual((f.r.present,f.r.active,f.g.powered),(0,0,0))
        self.assertEqual(bytes(f.r.card.uid),bytes(10))
        for payload in (gate.VERSION,b'',b'',b'',b''):f.respond(payload)
        self.assertLessEqual(f.sent()[len(before):].count(bytes.fromhex('d44001')),1)
        self.assertNotIn(IDM,bytes(f.r.pn.frame))
