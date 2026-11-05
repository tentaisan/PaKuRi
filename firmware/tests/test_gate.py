# SPDX-License-Identifier: AGPL-3.0-only
"""USB/CCID/reader/PN532実Cの結合試験。USB/SFR/UARTだけを合成する。"""
import ctypes as c
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest

from test_card import type_a, type_b
from test_ccid_packet import Tx
from test_reader import Reader, R_DONE, R_IDLE, R_FAILED, R_APDU, VERSION
from test_pn532_transport import ACK, ACK_WAIT, RESPONSE, DONE, FAILED
from test_pn532_frame import response


class Gate(c.Structure):
    _fields_ = [("tx", Tx), ("header", c.c_uint8 * 10), ("parameters", c.c_uint8 * 8)] + [
        (name, c.c_uint16) for name in
        ("body_length", "body_received", "deadline", "next_poll", "next_extension", "abort_deadline", "now")
    ] + [(name, c.c_uint8) for name in
         ("job", "header_used", "out_at", "command", "sequence", "slot", "active", "powered",
          "response", "source", "interim", "background", "bg_type", "bg_tries", "reported",
          "aborting", "abort_matched", "abort_failed", "rx_closed", "bulk_first", "startup_retry")]


def command(kind, data=b"", sequence=7, slot=0, p0=0, p1=0, p2=0):
    return struct.pack("<BIBBBBB", kind, len(data), slot, sequence, p0, p1, p2) + data


class GateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="pakuri-gate-")
        cls.addClassCleanup(cls.tmp.cleanup)
        root = Path(__file__).resolve().parents[1]
        out = Path(cls.tmp.name) / "gate.so"
        sources = [root / "src" / (name + ".c") for name in
                   ("gate", "reader", "card", "pn532_transport", "pn532_frame", "ccid_packet")]
        extra_flags=list(getattr(cls,'extra_flags',()))
        if '-DMG_EVENTS' in extra_flags:sources.append(root/'src/events.c')
        if '-DMG_SOFT_B' in extra_flags:sources.append(root/'src/isodep_b.c')
        if '-DMG_COMPACT_ABI' in extra_flags:sources.append(root/'tests/compact_abi_exports.c')
        if '-DMG_CH559_CLASSIC' in extra_flags:sources.append(root/'experimental/mifare/classic.c')
        if '-DMG_CH559_FELICA' in extra_flags:sources.append(root/'experimental/felica/read.c')
        if '-DMG_STANDALONE_OBSERVER' in extra_flags:
            sources.extend(root/'experimental/standalone'/name for name in ('state.c','observer.c'))
        if '-DMG_DISPATCH_CONSUMER_1=dispatch_probe_1' in extra_flags:
            sources.extend((root/'experimental/standalone/dispatch.c',root/'tests/dispatch_consumers.c'))
        if getattr(cls,'timing_mode',False):
            sources.append(root/'src/timing.c')
            extra_flags+=['-DMG_TIMING','-DCH552_HOST_TEST=']
        subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-shared", "-fPIC",
                        "-DMG_SINGLETON", "-DMG_CCID_TX_ONLY", "-fsanitize=undefined", "-fno-sanitize-recover=all",
                        *extra_flags, *(str(p) for p in sources), str(root / "tests/usb_harness.c"),
                        str(root / "tests/transport_uart_mock.c"), "-o", str(out)], check=True)
        cls.lib = c.CDLL(str(out))
        cls.lib.gate_init.argtypes = cls.lib.gate_poll.argtypes = [c.c_uint16]
        cls.lib.test_transfer.argtypes = [c.c_uint8, c.c_uint8]
        cls.lib.test_feed.argtypes = [c.c_uint8]
        cls.lib.test_tx_at.argtypes = [c.c_uint16]
        cls.lib.test_tx_at.restype = c.c_uint8
        cls.lib.test_tx_length.restype = c.c_uint16

    def setUp(self):
        self.now = 0
        self.lib.uart_init(); self.lib.test_usb_init(); self.lib.gate_init(0)
        self.g = Gate.in_dll(self.lib, "gate_state")
        self.r = Reader.in_dll(self.lib, "reader_state")
        self.ep0 = (c.c_uint8 * 64).in_dll(self.lib, "usb_ep0")
        self.ep1 = (c.c_uint8 * 64).in_dll(self.lib, "usb_ep1")
        self.ep2 = (c.c_uint8 * 128).in_dll(self.lib, "usb_ep2")
        self.setup(0, 9, 1)
        self.transfer(0x20, 0)

    def get(self, name):
        return c.c_uint8.in_dll(self.lib, name).value

    def poll(self, advance=1):
        self.now = (self.now + advance) & 65535
        self.lib.usb_device_poll(); self.lib.gate_poll(self.now)

    def transfer(self, token, length):
        self.lib.test_transfer(token, length); self.poll()

    def setup(self, kind, request, value=0, index=0, length=0):
        self.ep0[:8] = struct.pack("<BBHHH", kind, request, value, index, length)
        self.transfer(0x30, 8)

    def send(self, data, first=64):
        packets = [data[:first]] + [data[i:i + 64] for i in range(first, len(data), 64)]
        for packet in packets:
            for _ in range(1000):
                if self.get("UEP2_CTRL") & 12 == 0:
                    break
                self.poll()
            else:
                self.fail("OUTのNAKが解除されない")
            self.ep2[:len(packet)] = packet
            self.transfer(0x42, len(packet))

    def respond(self, payload):
        for _ in range(1000):
            if self.r.pn.phase == ACK_WAIT:
                break
            self.poll()
            self.assertNotEqual(self.r.phase, R_FAILED)
        else:
            self.fail(f"PN532 ACK待ちにならない: reader={self.r.phase}, gate={self.g.job}")
        for byte in ACK + response(payload, command=(self.r.pn.command + 1) & 255):
            self.lib.test_feed(byte)
        for _ in range(20):
            self.poll()
            if self.r.pn.phase not in (ACK_WAIT, RESPONSE):
                return
        self.fail("PN532応答を消費できない")

    def initialize(self):
        for payload in (VERSION, b"", b"", b""):
            self.respond(payload)
        self.assertEqual(self.r.initialized, 1)

    def collect(self):
        data, sizes = bytearray(), []
        for _ in range(2000):
            if not self.get("usb_in_armed") or self.get("UEP2_CTRL") & 3:
                self.poll(); continue
            length = self.get("UEP2_T_LEN")
            data += bytes(self.ep2)[64:64 + length]; sizes.append(length)
            self.transfer(0x22, 0)
            if length < 64:
                self.assertGreaterEqual(len(data), 10)
                self.assertEqual(len(data), 10 + int.from_bytes(data[1:5], "little"))
                return bytes(data), sizes
        self.fail(f"CCID応答が来ない: job={self.g.job}, reader={self.r.phase}")

    def final(self):
        for _ in range(10):
            message, sizes = self.collect()
            if message[7] & 0xC0 != 0x80:
                return message, sizes
        self.fail("時間延長しか返らない")

    def power_on(self, kind=0):
        self.send(command(0x62))
        self.respond(b"")
        if kind == 3:
            self.respond(b"\0")
        self.respond(type_a() if kind == 0 else type_b())
        message, _ = self.final()
        self.assertEqual((message[0], message[6], message[7], message[8]), (0x80, 7, 0, 0))
        self.assertEqual(message[10:], bytes(self.r.card.atr[:self.r.card.atr_length]))
        self.assertEqual((self.g.powered, self.r.active), (1, 1))

    def sent(self):
        return bytes(self.lib.test_tx_at(i) for i in range(self.lib.test_tx_length()))

    def abort(self, sequence=41):
        self.setup(0x21, 1, sequence << 8)
        self.transfer(0x20, 0)
        self.send(command(0x72, sequence=sequence))

    def notifications(self):
        for _ in range(3):
            if self.get("UEP1_CTRL") & 3:
                return
            self.transfer(0x21, 0)

    def test_slot_status_is_final_only_during_initialization(self):
        self.send(command(0x65, sequence=19), first=3)
        reply, sizes = self.collect()
        self.assertEqual(reply, bytes.fromhex("81000000000013020003"))
        self.assertEqual(sizes, [10])

    def test_power_on_type_a_and_b_dynamic_atr(self):
        for kind in (0, 3):
            with self.subTest(kind=kind):
                self.setUp(); self.initialize(); self.power_on(kind)

    def test_maximum_apdu_and_multiple_usb_response_packets(self):
        self.initialize(); self.power_on()
        apdu = bytes([0, 0xA4, 4, 0, 255]) + bytes(256)
        self.send(command(0x6F, apdu, sequence=23))
        self.assertEqual(self.r.pn.total, 274)
        data = bytes(range(256)) + b"\x90\0"
        self.respond(b"\0" + data)
        reply, sizes = self.final()
        self.assertEqual(reply[:10], bytes.fromhex("80020100000017000000"))
        self.assertEqual(reply[10:], data)
        self.assertEqual(sizes, [64, 64, 64, 64, 12])
        self.assertEqual(self.g.active, 0)
        self.assertEqual(bytes(self.r.pn.frame), bytes(275))

    def test_full_final_packet_requires_zlp_before_releasing_frame(self):
        self.initialize(); self.power_on()
        self.send(command(0x6F, bytes(4)))
        data = bytes(52) + b"\x90\0"
        self.respond(b"\0" + data)
        for _ in range(20):
            self.poll()
            if self.get("usb_in_armed"):
                break
        self.assertEqual(self.get("UEP2_T_LEN"), 64)
        retained = bytes(self.r.pn.frame)
        self.transfer(0x22, 0)
        self.assertEqual(self.get("usb_in_armed"), 1)
        self.assertEqual(self.get("UEP2_T_LEN"), 0)
        self.assertEqual(bytes(self.r.pn.frame), retained)
        self.transfer(0x22, 0)
        self.assertEqual((self.g.active, self.r.phase), (0, R_IDLE))
        self.assertEqual(bytes(self.r.pn.frame), bytes(275))

    def test_power_off_has_no_time_extension_and_disables_apdu(self):
        self.initialize(); self.power_on()
        self.send(command(0x63))
        self.respond(b"")
        reply, sizes = self.collect()
        self.assertEqual((reply[0], reply[7], reply[8]), (0x81, 1, 0))
        self.assertEqual(sizes, [10])
        self.send(command(0x6F, bytes(4)))
        reply, _ = self.collect()
        self.assertEqual((reply[7], reply[8]), (0x41, 0xFE))

    def test_short_extended_apdu_and_bad_slot_are_rejected_without_uart(self):
        self.initialize(); self.power_on()
        before = self.sent()
        for request, error in ((command(0x6F, bytes(7)), 1),
                               (command(0x6F, bytes(4), slot=1), 5),
                               (command(0x6F, bytes(4), p1=1), 8),
                               (command(0x69), 0)):
            self.send(request)
            reply, _ = self.collect()
            self.assertEqual(reply[7] & 0xC0, 0x40)
            self.assertEqual(reply[8], error)
        self.assertEqual(self.sent(), before)

    def test_parameters_rate_and_unsupported_escape(self):
        self.initialize()
        for request, payload, error in (
            (command(0x6C), bytes.fromhex("1110004d00fe00"), 0),
            (command(0x61, bytes.fromhex("1110004d00fe00"), p0=1), bytes.fromhex("1110004d00fe00"), 0),
            (command(0x61, bytes(7), p0=1), b"", 10),
            (command(0x73, bytes.fromhex("a00f000080250000")), bytes.fromhex("a00f000080250000"), 0),
            (command(0x6B, b""), b"", 0)):
            self.send(request)
            reply, _ = self.collect()
            self.assertEqual(reply[10:], payload)
            self.assertEqual(reply[8], error)
        self.assertEqual(reply[7] & 0xC0, 0x40)

    def test_time_extension_for_waiting_apdu_then_final_reply(self):
        self.initialize(); self.power_on()
        self.send(command(0x6F, bytes(4), sequence=31))
        self.poll(300)
        reply, _ = self.collect()
        self.assertEqual((reply[6], reply[7], reply[8]), (31, 0x80, 1))
        self.respond(bytes.fromhex("009000"))
        reply, _ = self.final()
        self.assertEqual(reply[10:], b"\x90\0")

    def test_sustained_pn_wait_preserves_deadline_and_maximum_reply(self):


        for kind in (0, 3):
            with self.subTest(kind=kind):
                self.setUp(); self.initialize(); self.power_on(kind)
                before = len(self.sent())
                self.send(command(0x6F, bytes(4), sequence=31))
                for _ in range(1000):
                    if self.r.pn.phase == ACK_WAIT:break
                    self.poll()
                self.assertEqual(self.r.pn.phase, ACK_WAIT)
                for byte in ACK:self.lib.test_feed(byte)
                self.poll()
                deadline = self.g.deadline
                for _ in range(24):
                    self.poll(250)
                    extension, sizes = self.collect()
                    self.assertEqual((len(extension), extension[6:10], sizes),
                                     (10, bytes((31, 0x80, 1, 0)), [10]))
                    self.assertEqual((self.g.deadline, self.r.pn.deadline),
                                     (deadline, deadline))
                    self.assertEqual(self.r.pn.phase, RESPONSE)
                data = bytes(range(256)) + b'\x90\0'

                for byte in response(b'\0' + data, command=0x41):self.lib.test_feed(byte)
                reply, sizes = self.final()
                self.assertEqual((reply[6:10], reply[10:]), (bytes((31, 0, 0, 0)), data))
                self.assertEqual(sizes, [64, 64, 64, 64, 12])
                self.assertEqual(self.sent()[before:].count(bytes.fromhex('d44001')), 1)

    def test_abort_partial_tx_and_fresh_session_without_apdu_replay(self):
        self.initialize(); self.power_on()
        before = self.sent()
        self.send(command(0x6F, bytes.fromhex("00a4040000")))
        self.poll()
        self.abort()
        self.assertEqual(self.g.powered, 0)
        self.initialize()
        reply, _ = self.collect()
        self.assertEqual((reply[0], reply[6], reply[7] & 0xC0, reply[8]), (0x81, 41, 0, 0))

        self.assertEqual(self.sent()[len(before):].count(bytes.fromhex("d44001")), 1)
        self.send(command(0x6F, bytes(4)))
        reply, _ = self.collect()
        self.assertEqual(reply[8], 0xFE)

    def test_abort_bulk_first_and_control_second(self):
        self.initialize()
        self.send(command(0x72, sequence=33))
        self.assertEqual(self.g.bulk_first, 1)
        self.setup(0x21, 1, 33 << 8)
        self.transfer(0x20, 0)
        self.initialize()
        reply, _ = self.collect()
        self.assertEqual((reply[0], reply[6], reply[8]), (0x81, 33, 0))

    def test_abort_rejects_other_commands_until_matching_pair(self):
        self.initialize(); self.setup(0x21, 1, 35 << 8)
        self.transfer(0x20, 0)
        self.send(command(0x65, sequence=8))
        reply, _ = self.collect()
        self.assertEqual((reply[6], reply[7] & 0xC0, reply[8]), (8, 0x40, 0xFF))
        self.send(command(0x72, sequence=36))
        reply, _ = self.collect()
        self.assertEqual(reply[8], 0xFF)
        self.send(command(0x72, sequence=35))
        self.initialize()
        reply, _ = self.collect()
        self.assertEqual((reply[6], reply[8]), (35, 0))

    def test_partial_header_timeout_closes_out_until_abort_or_reset(self):
        self.send(b"\x6f\x04\0")
        self.poll(1100)
        self.assertEqual(self.g.rx_closed, 1)
        self.assertEqual(self.get("usb_accept_out"), 0)
        self.lib.test_reset(); self.poll()
        self.assertEqual(self.g.rx_closed, 0)

    def test_oversize_length_is_not_written_to_shared_frame(self):
        self.initialize(); self.power_on()
        retained = bytes(self.r.pn.frame)
        request = bytearray(command(0x6F))
        request[1:5] = (262).to_bytes(4, "little")
        self.send(bytes(request))
        reply, _ = self.collect()
        self.assertEqual((reply[8], self.g.rx_closed), (1, 1))
        self.assertEqual(bytes(self.r.pn.frame), retained)

    def test_usb_reset_cancels_pending_response_without_replay(self):
        self.initialize(); self.power_on()
        self.send(command(0x6F, bytes(4)))
        self.respond(bytes.fromhex("009000"))
        before = self.sent()
        self.lib.test_reset(); self.poll()
        self.assertEqual((self.g.powered, self.g.active, self.get("usb_in_armed")), (0, 0, 0))
        self.assertEqual(self.get("usb_configured"), 0)
        self.initialize()
        self.assertNotIn(bytes.fromhex("d44001"), self.sent()[len(before):])

    def test_background_presence_retains_out_until_shared_frame_is_free(self):
        self.initialize(); self.power_on(); self.notifications(); self.poll(200)
        self.assertEqual(self.g.background, 2)
        retained = bytes(self.r.pn.frame)
        apdu = bytes.fromhex("00a4040000")
        self.send(command(0x6F, apdu))
        self.assertEqual(self.get("usb_out_pending"), 1)
        self.assertEqual(self.g.out_at, 10)
        self.assertEqual(bytes(self.r.pn.frame), retained)
        self.respond(bytes.fromhex("00a2"))
        self.assertEqual(self.get("usb_out_pending"), 0)
        self.assertEqual(self.r.pn.command, 0x40)
        self.respond(bytes.fromhex("009000"))
        reply, _ = self.final()
        self.assertEqual(reply[10:], b"\x90\0")

    def test_before_power_on_uart_failure_recovers_once_then_detects_card(self):
        self.initialize(); self.notifications()
        self.lib.test_feed(0xaa); self.poll()
        self.assertEqual(self.r.phase, R_FAILED)
        self.poll(200)
        self.assertNotEqual(self.r.phase, R_FAILED)
        self.initialize(); self.notifications(); self.poll(200)
        self.respond(b'\0'); self.respond(type_b())
        self.assertEqual((self.r.present, self.r.active, self.g.powered), (1, 0, 0))
        self.assertEqual(bytes(self.ep1[:2]), b'\x50\x03')
        self.assertNotIn(bytes.fromhex('d44001'), self.sent())

    def test_startup_recovery_budget_is_not_replenished_by_success_or_polling(self):
        self.initialize(); self.lib.test_feed(0xaa); self.poll(); self.poll(200)
        self.assertNotEqual(self.r.phase, R_FAILED)
        self.initialize()
        self.lib.test_feed(0xaa); self.poll()
        self.assertEqual(self.r.phase, R_FAILED)
        before=self.sent()
        for _ in range(5):self.poll(2000)
        self.assertEqual((self.r.phase, self.sent()), (R_FAILED, before))

    def test_after_power_on_uart_failure_stays_closed_without_auto_recovery(self):
        self.initialize(); self.power_on(); self.notifications()
        self.lib.test_feed(0xaa); self.poll()
        self.assertEqual(self.r.phase, R_FAILED)
        before=self.sent()
        for _ in range(5):self.poll(2000)
        self.assertEqual((self.r.phase, self.sent()), (R_FAILED, before))

    def test_partial_usb_header_defers_startup_recovery(self):
        self.initialize(); self.lib.test_feed(0xaa); self.poll()
        self.send(command(0x65)[:3]); self.poll(200)
        self.assertEqual((self.r.phase, self.g.header_used), (R_FAILED, 3))

    def test_non_uart_startup_failure_remains_closed(self):
        self.initialize()
        self.r.pn.phase=FAILED; self.r.pn.error=33; self.poll()
        before=self.sent(); self.poll(2000)
        self.assertEqual((self.r.phase, self.sent(), self.g.startup_retry), (R_FAILED, before, 1))

    def test_usb_reset_renews_startup_budget_without_replaying_old_apdu(self):
        self.initialize(); self.power_on()
        self.assertEqual(self.g.startup_retry, 0)
        self.lib.test_reset(); self.poll()
        self.setup(0, 9, 1); self.transfer(0x20, 0)
        self.initialize(); self.lib.test_feed(0xaa); self.poll(); self.poll(200)
        self.assertNotEqual(self.r.phase, R_FAILED)
        self.assertEqual(self.g.startup_retry, 0)
        self.assertNotIn(bytes.fromhex('d44001'), self.sent())

    def test_replacement_waits_for_removal_notification_and_is_inactive(self):
        self.initialize(); self.power_on(); self.notifications(); self.poll(200)
        self.respond(b"\x01")
        self.assertEqual((self.g.powered, self.g.reported), (0, 0))
        self.assertEqual(bytes(self.ep1[:2]), b"\x50\x02")
        self.poll(200)
        self.assertEqual(self.g.background, 0)
        self.notifications(); self.poll(200)
        self.assertEqual(self.g.background, 1)
        self.respond(b"\0"); self.respond(type_b())
        self.assertEqual((self.r.present, self.r.active, self.g.powered), (1, 0, 0))
        self.assertEqual(bytes(self.ep1[:2]), b"\x50\x03")
        self.send(command(0x6F, bytes(4)))
        reply, _ = self.collect()
        self.assertEqual(reply[8], 0xFE)

    def test_power_on_absent_card_tries_both_types(self):
        self.initialize(); self.send(command(0x62))
        self.respond(b""); self.respond(b"\0"); self.respond(b"\0")
        reply, _ = self.final()
        self.assertEqual((reply[0], reply[7], reply[8]), (0x80, 0x42, 0xFE))
        self.assertEqual((self.r.present, self.g.powered), (0, 0))

    def test_power_off_waiting_does_not_emit_intermediate_status(self):
        self.initialize(); self.power_on(); self.send(command(0x63)); self.poll(300)
        self.assertEqual(self.get("usb_in_armed"), 0)
        self.assertEqual(self.g.response, 0)
        self.respond(b"")
        reply, _ = self.collect()
        self.assertEqual(reply[7] & 0xC0, 0)

    def test_apdu_timeout_closes_connection_without_replay(self):
        self.initialize(); self.power_on(); before = self.sent()
        self.send(command(0x6F, bytes(4)))
        self.poll(16000)
        reply, _ = self.final()
        self.assertEqual(reply[8], 0xFE)
        self.assertEqual((self.r.phase, self.g.powered), (R_FAILED, 0))
        self.send(command(0x6F, bytes(4)))
        reply, _ = self.collect()
        self.assertEqual(reply[8], 0xFE)
        self.assertLessEqual(self.sent()[len(before):].count(bytes.fromhex("d44001")), 1)

    def silent_response_deadline(self, start):
        self.initialize(); self.power_on()
        self.now = start; self.g.next_poll = (start + 150) & 65535
        before = len(self.sent())
        self.send(command(0x6F, bytes(4), sequence=73))
        for _ in range(1000):
            if self.r.pn.phase == ACK_WAIT:break
            self.poll()
        self.assertEqual(self.r.pn.phase, ACK_WAIT)
        for byte in ACK:self.lib.test_feed(byte)
        self.poll()
        self.assertEqual(self.r.pn.phase, RESPONSE)
        deadline = self.g.deadline
        self.assertEqual(self.r.pn.deadline, deadline)
        self.poll((deadline - self.now - 2) & 65535)
        extension, _ = self.collect()
        self.assertEqual(extension[7] & 0xC0, 0x80)
        self.assertEqual(self.now, (deadline - 1) & 65535)
        self.assertEqual(self.r.pn.phase, RESPONSE)
        self.poll()
        self.assertEqual(self.now, deadline)
        reply, _ = self.final()
        self.assertEqual((len(reply), reply[6], reply[8]), (10, 73, 0xFE))
        self.assertEqual((self.r.phase, self.r.active, self.r.selected, self.g.powered), (R_FAILED, 0, 0, 0))

        for byte in response(b"\0\x6a\x82", command=0x41):self.lib.test_feed(byte)
        self.poll(10)
        self.assertEqual(self.sent()[before:].count(bytes.fromhex('d44001')), 1)
        self.send(command(0x62, sequence=74)); self.initialize()
        self.respond(b""); self.respond(type_a())
        fresh, _ = self.final()
        self.assertEqual((fresh[6], fresh[7], fresh[8]), (74, 0, 0))
        self.send(command(0x6F, bytes(4), sequence=75))
        self.respond(b"\0\x90\0")
        fresh, _ = self.final()
        self.assertEqual((fresh[6], fresh[10:]), (75, b"\x90\0"))

    def test_acknowledged_silent_response_deadline_and_fresh_recovery(self):
        self.silent_response_deadline(1000)

    def test_acknowledged_silent_response_deadline_wrap_and_fresh_recovery(self):
        self.silent_response_deadline(65000)

    def test_receive_deadline_wrap_and_incomplete_body(self):
        self.initialize(); self.power_on()
        self.now = 65530; self.g.next_poll = (self.now + 150) & 65535
        self.send(command(0x6F, bytes(4))[:10])
        self.poll(1100)
        reply, _ = self.collect()
        self.assertEqual((reply[8], self.g.rx_closed), (0xFE, 1))
        self.assertEqual(self.get("usb_accept_out"), 0)

    def test_abort_after_partial_usb_response_discards_remainder(self):
        self.initialize(); self.power_on()
        self.send(command(0x6F, bytes(4)))
        self.respond(b"\0" + bytes(130) + b"\x90\0")
        for _ in range(20):
            self.poll()
            if self.get("usb_in_armed"):
                break
        self.assertEqual(self.get("UEP2_T_LEN"), 64)
        self.transfer(0x22, 0)
        self.abort(sequence=49)
        self.initialize()
        reply, sizes = self.collect()
        self.assertEqual((reply[0], reply[6], reply[8], sizes), (0x81, 49, 0, [10]))

    def test_repeated_control_abort_does_not_extend_cleanup_deadline(self):
        self.initialize(); self.setup(0x21, 1, 53 << 8)
        deadline = self.g.abort_deadline
        self.poll(100); self.setup(0x21, 1, 53 << 8)
        self.assertEqual(self.g.abort_deadline, deadline)
        self.send(command(0x72, sequence=53)); self.initialize()
        reply, _ = self.collect()
        self.assertEqual((reply[6], reply[8]), (53, 0))

    def test_unpaired_bulk_abort_does_not_destroy_active_card(self):
        self.initialize(); self.power_on(); before = self.sent()
        self.send(command(0x72, sequence=61)); self.poll(3100)
        reply, _ = self.collect()
        self.assertEqual((reply[6], reply[7], reply[8]), (61, 0x40, 0xFF))
        self.assertEqual((self.g.powered, self.r.active), (1, 1))
        self.assertEqual(self.sent(), before)

    def test_apdu_and_response_boundary_matrix(self):

        commands = (4, 5, 6, 7, 63, 64, 65, 251, 252, 253, 254, 260, 261)
        responses = (2, 53, 54, 55, 117, 118, 119, 181, 182, 183, 245, 246,
                     247, 250, 251, 252, 253, 254, 255, 256, 257, 258)
        for ci, length in enumerate(commands):
            for ri, size in enumerate(responses):
                with self.subTest(command_bytes=length, response_bytes=size):
                    self.setUp(); self.initialize(); self.power_on()
                    if length <= 5:
                        apdu = bytes([0, 0xCA, 0, 0]) + (b"\0" if length == 5 else b"")
                    else:
                        lc = min(length - 5, 255)
                        apdu = bytes([0, 0xA4, 4, 0, lc]) + bytes([0x5A]) * lc
                        if len(apdu) < length:
                            apdu += b"\0"
                    before = len(self.sent())
                    sequence = (ci * len(responses) + ri) & 255
                    first = (1, 9, 10, 11, 63, 64)[(ci + ri) % 6]
                    self.send(command(0x6F, apdu, sequence=sequence), first=first)
                    payload = bytes((i * 31 + size) & 255 for i in range(size - 2)) + b"\x90\0"
                    self.respond(b"\0" + payload)
                    reply, sizes = self.final()
                    self.assertEqual(reply[6:10], bytes([sequence, 0, 0, 0]))
                    self.assertEqual(reply[10:], payload)
                    total = 10 + size
                    self.assertEqual(sizes, [64] * (total // 64) + [total % 64])
                    self.assertEqual(self.sent()[before:], response(b"\x01" + apdu, 0xD4, 0x40))
                    self.assertEqual((self.g.active, self.r.phase), (0, R_IDLE))
                    self.assertEqual(bytes(self.r.pn.frame), bytes(275))

    def test_halt_clear_during_response_never_resumes_old_payload(self):
        for endpoint in (2, 0x82):
            for size in (54, 118, 258):
                with self.subTest(endpoint=endpoint, response_bytes=size):
                    self.setUp(); self.initialize(); self.power_on()
                    self.send(command(0x6F, bytes(4)))
                    self.respond(b"\0" + bytes(size - 2) + b"\x90\0")
                    self.transfer(0x22, 0)
                    before = len(self.sent())
                    self.setup(2, 3, index=endpoint)
                    self.setup(2, 1, index=endpoint)
                    self.assertEqual((self.g.powered, self.g.active, self.g.response), (0, 0, 0))
                    self.assertEqual(self.get("usb_in_armed"), 0)
                    self.initialize()
                    self.assertNotIn(bytes.fromhex("d44001"), self.sent()[before:])
                    self.send(command(0x6F, bytes(4), sequence=81))
                    reply, sizes = self.collect()
                    self.assertEqual((reply[6], reply[8], sizes), (81, 0xFE, [10]))

    def test_fifo_fault_discards_response_until_bus_reset(self):
        self.initialize(); self.power_on()
        self.send(command(0x6F, bytes(4)))
        self.respond(b"\0" + bytes(128) + b"\x90\0")
        before = len(self.sent())
        c.c_uint8.in_dll(self.lib, "USB_INT_FG").value = 0x10
        self.poll()
        self.assertEqual((self.g.powered, self.g.active, self.g.response, self.g.rx_closed), (0, 0, 0, 1))
        self.assertEqual(self.get("usb_in_armed"), 0)
        self.initialize()
        self.assertEqual(self.get("UEP2_CTRL") & 12, 8)
        self.assertEqual(self.get("usb_in_armed"), 0)
        self.lib.test_reset(); self.poll()
        self.setup(0, 9, 1); self.transfer(0x20, 0)
        self.initialize()
        self.assertNotIn(bytes.fromhex("d44001"), self.sent()[before:])
        self.send(command(0x65, sequence=82))
        reply, sizes = self.collect()
        self.assertEqual((reply[6], reply[7], sizes), (82, 2, [10]))


    def test_abort_snapshot_captures_original_wait_phase_for_both_orders(self):
        for bulk_first in (False, True):
            for pending_phase in (ACK_WAIT, RESPONSE):
                with self.subTest(bulk_first=bulk_first, pending_phase=pending_phase):
                    self.setUp(); self.initialize(); self.power_on(kind=3)
                    self.send(command(0x6F, bytes.fromhex('00b0000000')))
                    for _ in range(100):
                        if self.r.pn.phase == ACK_WAIT:break
                        self.poll()
                    self.assertEqual(self.r.pn.phase, ACK_WAIT)
                    if pending_phase == RESPONSE:
                        for byte in ACK:self.lib.test_feed(byte)
                        self.poll()
                    self.assertEqual((self.r.phase, self.r.pn.phase), (9, pending_phase))
                    if bulk_first:self.send(command(0x72))
                    self.setup(0x21, 1, 7 << 8); self.transfer(0x20, 0)
                    if not bulk_first:self.send(command(0x72))
                    expected = bytes((7, 9, pending_phase))
                    def observe():
                        if getattr(self,'timing_mode',False):
                            self.setup(0xc0,0x5d,length=3)
                            self.assertEqual(self.get('UEP0_CTRL'),0x0f)
                        else:
                            snapshot=(c.c_uint8*3).in_dll(self.lib,'usb_abort_snapshot')
                            self.assertEqual(bytes(snapshot),expected)
                    observe()
                    self.setup(0x21, 1, 7 << 8); self.transfer(0x20, 0)
                    self.send(command(0x72))
                    observe()
                    self.initialize(); self.final()
                    observe()


if __name__ == "__main__":
    unittest.main()
