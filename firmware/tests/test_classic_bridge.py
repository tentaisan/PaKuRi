# SPDX-License-Identifier: Apache-2.0
"""Host-only integration of MIFARE logic and actual PN532 transport."""
import ctypes as c
from pathlib import Path
import subprocess
import tempfile
import unittest
import struct

from test_pn532_frame import array, response
import test_pn532_transport as transport
from test_ccid_packet import Rx

State, ACK, ACK_WAIT, READY = transport.State, transport.ACK, transport.ACK_WAIT, transport.READY


class Card(c.Structure):
    _fields_ = [('key', c.c_uint8 * 6), ('uid', c.c_uint8 * 4)] + [
        (name, c.c_uint8) for name in ('key_loaded', 'present', 'pending', 'authenticated', 'sector')]


class Bridge(c.Structure):
    _fields_ = [('card', Card), ('pn', c.POINTER(State)), ('response', c.c_uint8 * 18),
                ('response_len', c.c_size_t), ('state', c.c_uint8)]


class Ccid(c.Structure):
    _fields_ = [('bridge', c.POINTER(Bridge)), ('active', c.c_uint8), ('sequence', c.c_uint8)]


class ClassicBridgeTests(transport.TransportTests):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='pakuri-classic-bridge-')
        cls.addClassCleanup(cls.tmp.cleanup)
        root = Path(__file__).resolve().parents[1]
        out = Path(cls.tmp.name) / 'bridge.so'
        sources = ['src/pn532_transport.c', 'src/pn532_frame.c', 'src/ccid_packet.c', 'tests/transport_uart_mock.c',
                   'experimental/mifare/classic.c', 'experimental/mifare/bridge.c',
                   'experimental/mifare/ccid_bridge.c']
        subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-shared', '-fPIC',
                        '-fsanitize=undefined', '-fno-sanitize-recover=all',
                        *(str(root / name) for name in sources), '-o', str(out)], check=True)
        cls.lib = c.CDLL(str(out))
        state, byte, bridge = c.POINTER(State), c.POINTER(c.c_uint8), c.POINTER(Bridge)
        cls.lib.pn_transport_init.argtypes = [state]
        cls.lib.pn_transport_poll.argtypes = [state, c.c_uint16]
        cls.lib.pn_transport_recover.argtypes = [state, c.c_uint16]
        cls.lib.test_feed.argtypes = [c.c_uint8]
        cls.lib.test_tx_at.argtypes = [c.c_uint16]; cls.lib.test_tx_at.restype = c.c_uint8
        cls.lib.test_tx_length.restype = c.c_uint16
        cls.lib.mb_init.argtypes = [bridge, state]
        cls.lib.mb_attach.argtypes = [bridge, byte, c.c_size_t]
        cls.lib.mb_submit.argtypes = [bridge, byte, c.c_size_t, c.c_uint16]
        cls.lib.mb_poll.argtypes = [bridge, c.c_uint16]
        cls.lib.mb_invalidate.argtypes = [bridge, c.c_uint16]
        cls.lib.mb_take.argtypes = [bridge, byte, c.c_size_t, c.POINTER(c.c_size_t)]
        cls.lib.mfc_init.argtypes = [c.POINTER(Ccid), bridge]
        cls.lib.mfc_submit.argtypes = [c.POINTER(Ccid), byte, c.c_size_t, c.c_uint16]
        cls.lib.mfc_poll.argtypes = [c.POINTER(Ccid), c.c_uint16]
        cls.lib.mfc_take.argtypes = [c.POINTER(Ccid), byte, c.c_size_t, c.POINTER(c.c_size_t)]
        cls.lib.mfc_invalidate.argtypes = [c.POINTER(Ccid), c.c_uint16]
        cls.lib.ccid_rx_init.argtypes = [c.POINTER(Rx), c.c_uint16]
        cls.lib.ccid_rx_push.argtypes = [c.POINTER(Rx), byte, c.c_uint8, byte, byte, byte]

    def setUp(self):
        self.state = State(); self.now = 0
        self.lib.uart_init(); self.lib.pn_transport_init(c.byref(self.state)); self.recover()
        self.bridge = Bridge(); self.lib.mb_init(c.byref(self.bridge), c.byref(self.state))
        self.assertEqual(self.lib.mb_attach(c.byref(self.bridge), array(b'\x01\x02\x03\x04'), 4), 1)

    def command(self, value):
        return self.lib.mb_submit(c.byref(self.bridge), array(value), len(value), self.now)

    def take(self):
        out = (c.c_uint8 * 18)(); length = c.c_size_t()
        self.assertEqual(self.lib.mb_take(c.byref(self.bridge), out, len(out), c.byref(length)), 1)
        return bytes(out[:length.value])

    def poll_bridge(self, advance=1):
        self.now = (self.now + advance) & 65535
        self.lib.mb_poll(c.byref(self.bridge), self.now)

    def exchange(self, reply):
        for _ in range(1000):
            self.poll_bridge()
            if self.state.phase == ACK_WAIT: break
        else: self.fail('PN532 ACK待ちに到達しない')
        self.feed(ACK + response(reply, command=0x41))
        for _ in range(1000):
            self.poll_bridge()
            if self.bridge.state == 2: return self.take()
        self.fail('PN532応答を処理できない')

    def load_key(self):
        self.assertEqual(self.command(bytes.fromhex('ff82000006010203040506')), 1)
        self.assertEqual(self.take(), bytes.fromhex('9000'))

    def authenticate(self):
        self.assertEqual(self.command(bytes.fromhex('ff860000050100046000')), 1)
        return self.exchange(b'\x00')

    def test_key_authentication_and_read_through_transport(self):
        self.load_key(); self.assertEqual(self.authenticate(), bytes.fromhex('9000'))
        self.assertEqual(self.command(bytes.fromhex('ffb0000410')), 1)
        payload = bytes(range(16))
        self.assertEqual(self.exchange(b'\x00' + payload), payload + bytes.fromhex('9000'))
        self.assertEqual(self.state.phase, READY)
        self.assertEqual(bytes(self.state.frame), bytes(275))

    def test_write_and_reselection_invalidate_session(self):
        self.load_key(); self.authenticate()
        self.assertEqual(self.command(bytes.fromhex('ffd6000410') + bytes(range(16))), 1)
        self.assertEqual(self.exchange(b'\x00'), bytes.fromhex('9000'))
        self.lib.mb_invalidate(c.byref(self.bridge), self.now)
        self.assertEqual(bytes(self.bridge.card.key), bytes(6))
        self.assertEqual(self.command(bytes.fromhex('ffb0000410')), 0)

    def test_timeout_clears_key_and_does_not_retry(self):
        self.load_key()
        before = len(self.sent())
        self.assertEqual(self.command(bytes.fromhex('ff860000050100046000')), 1)
        for _ in range(1000):
            self.poll_bridge()
            if self.state.phase == ACK_WAIT: break
        self.poll_bridge(15001)
        self.assertEqual(self.bridge.state, 3)
        self.assertEqual(bytes(self.bridge.card.key), bytes(6))
        self.assertEqual(self.sent()[before:].count(bytes.fromhex('d440016004')), 1)

    def test_failed_authentication_never_enables_read(self):
        self.load_key()
        self.assertEqual(self.command(bytes.fromhex('ff860000050100046000')), 1)
        self.assertEqual(self.exchange(b'\x14'), bytes.fromhex('6300'))
        self.assertEqual(self.command(bytes.fromhex('ffb0000410')), 1)
        self.assertEqual(self.take(), bytes.fromhex('6982'))

    def test_cancel_pending_exchange_clears_card_and_blocks_replay(self):
        self.load_key(); before = len(self.sent())
        self.assertEqual(self.command(bytes.fromhex('ff860000050100046000')), 1)
        for _ in range(1000):
            self.poll_bridge()
            if self.state.phase == ACK_WAIT: break
        self.lib.mb_invalidate(c.byref(self.bridge), self.now)
        self.assertEqual(self.bridge.state, 3)
        self.assertEqual(bytes(self.bridge.card.key), bytes(6))
        self.assertEqual(self.command(bytes.fromhex('ffb0000410')), 0)
        self.assertEqual(self.sent()[before:].count(bytes.fromhex('d440016004')), 1)
        self.assertEqual(self.lib.mb_attach(c.byref(self.bridge), array(b'\x01\x02\x03\x04'), 4), 0)

        self.until(transport.SEND); self.until(ACK_WAIT)
        self.feed(ACK + transport.VERSION); self.poll()
        self.assertEqual(self.state.phase, READY)
        self.assertEqual(bytes(self.state.frame), bytes(275))
        self.assertEqual(self.sent()[before:].count(bytes.fromhex('d440016004')), 1)

    def test_malformed_read_response_loses_authentication(self):
        self.load_key(); self.authenticate()
        self.assertEqual(self.command(bytes.fromhex('ffb0000410')), 1)
        self.assertEqual(self.exchange(b'\x00' + bytes(15)), bytes.fromhex('6300'))
        self.assertEqual(self.command(bytes.fromhex('ffb0000410')), 1)
        self.assertEqual(self.take(), bytes.fromhex('6982'))

    def test_ccid_envelope_to_pn532_and_back(self):
        adapter = Ccid(); self.lib.mfc_init(c.byref(adapter), c.byref(self.bridge))
        def request(apdu, sequence):
            message = struct.pack('<BIBBBBB', 0x6f, len(apdu), 0, sequence, 0, 0, 0) + apdu
            self.assertEqual(self.lib.mfc_submit(c.byref(adapter), array(message), len(message), self.now), 1)
            return message
        def take(sequence, data):
            out = (c.c_uint8 * 28)(); n = c.c_size_t()
            self.assertEqual(self.lib.mfc_take(c.byref(adapter), out, len(out), c.byref(n)), 1)
            expected = struct.pack('<BIBBBBB', 0x80, len(data), 0, sequence, 0, 0, 0) + data
            self.assertEqual(bytes(out[:n.value]), expected)
        request(bytes.fromhex('ff82000006010203040506'), 0x21); take(0x21, bytes.fromhex('9000'))
        message = request(bytes.fromhex('ff860000050100046000'), 0x22)
        self.assertEqual(self.lib.mfc_submit(c.byref(adapter), array(message), len(message), self.now), 0)
        for _ in range(1000):
            self.now += 1; self.lib.mfc_poll(c.byref(adapter), self.now)
            if self.state.phase == ACK_WAIT: break
        self.feed(ACK + response(b'\x00', command=0x41))
        for _ in range(1000):
            self.now += 1; self.lib.mfc_poll(c.byref(adapter), self.now)
            if self.bridge.state == 2: break
        take(0x22, bytes.fromhex('9000'))
        request(bytes.fromhex('ffb0000410'), 0x23)
        for _ in range(1000):
            self.now += 1; self.lib.mfc_poll(c.byref(adapter), self.now)
            if self.state.phase == ACK_WAIT: break
        data = bytes(range(16)); self.feed(ACK + response(b'\x00'+data, command=0x41))
        for _ in range(1000):
            self.now += 1; self.lib.mfc_poll(c.byref(adapter), self.now)
            if self.bridge.state == 2: break
        take(0x23, data + bytes.fromhex('9000'))
        self.lib.mfc_invalidate(c.byref(adapter), self.now)
        self.assertEqual(bytes(self.bridge.card.key), bytes(6))

    def test_ccid_invalid_frame_is_rejected_before_rf(self):
        adapter = Ccid(); self.lib.mfc_init(c.byref(adapter), c.byref(self.bridge))
        before = len(self.sent())
        for msg in (bytes.fromhex('6f050000000101000000ffb0000410'),
                    bytes.fromhex('6f060000000001000000ffb0000410')):
            self.assertEqual(self.lib.mfc_submit(c.byref(adapter), array(msg), len(msg), self.now), 0)
        self.assertEqual(len(self.sent()), before)

    def test_ccid_timeout_is_failed_reply_with_original_sequence(self):
        self.load_key()
        adapter = Ccid(); self.lib.mfc_init(c.byref(adapter), c.byref(self.bridge))
        apdu = bytes.fromhex('ff860000050100046000')
        message = struct.pack('<BIBBBBB', 0x6f, len(apdu), 0, 0x5a, 0, 0, 0) + apdu
        self.assertEqual(self.lib.mfc_submit(c.byref(adapter), array(message), len(message), self.now), 1)
        for _ in range(1000):
            self.now += 1; self.lib.mfc_poll(c.byref(adapter), self.now)
            if self.state.phase == ACK_WAIT: break
        self.now += 15001; self.lib.mfc_poll(c.byref(adapter), self.now)
        out = (c.c_uint8 * 28)(); n = c.c_size_t()
        self.assertEqual(self.lib.mfc_take(c.byref(adapter), out, len(out), c.byref(n)), 1)
        self.assertEqual(bytes(out[:n.value]), struct.pack('<BIBBBBB', 0x80, 0, 0, 0x5a, 0x42, 0xfe, 0))
        self.assertEqual(bytes(self.bridge.card.key), bytes(6))

    def test_ccid_reset_discards_queued_reply(self):
        adapter = Ccid(); self.lib.mfc_init(c.byref(adapter), c.byref(self.bridge))
        apdu = bytes.fromhex('ff82000006010203040506')
        message = struct.pack('<BIBBBBB', 0x6f, len(apdu), 0, 7, 0, 0, 0) + apdu
        self.assertEqual(self.lib.mfc_submit(c.byref(adapter), array(message), len(message), self.now), 1)
        self.lib.mfc_invalidate(c.byref(adapter), self.now)
        out = (c.c_uint8 * 28)(); n = c.c_size_t()
        self.assertEqual(self.lib.mfc_take(c.byref(adapter), out, len(out), c.byref(n)), 0)
        self.assertEqual(bytes(self.bridge.card.key), bytes(6))

    def test_split_ccid_request_is_reassembled_before_key_load(self):
        apdu = bytes.fromhex('ff82000006010203040506')
        message = struct.pack('<BIBBBBB', 0x6f, len(apdu), 0, 9, 0, 0, 0) + apdu
        rx = Rx(); self.lib.ccid_rx_init(c.byref(rx), 271)
        assembled = bytearray()
        for packet in (message[:4], message[4:11], message[11:]):
            consumed, written = c.c_uint8(), c.c_uint8(); output = (c.c_uint8 * 54)()
            self.assertEqual(self.lib.ccid_rx_push(c.byref(rx), array(packet), len(packet),
                c.byref(consumed), output, c.byref(written)), 1)
            self.assertEqual(consumed.value, len(packet))
            assembled.extend(output[:written.value])
        self.assertEqual(assembled, message)
        adapter = Ccid(); self.lib.mfc_init(c.byref(adapter), c.byref(self.bridge))
        self.assertEqual(self.lib.mfc_submit(c.byref(adapter), array(assembled), len(assembled), self.now), 1)
        out = (c.c_uint8 * 28)(); n = c.c_size_t()
        self.assertEqual(self.lib.mfc_take(c.byref(adapter), out, len(out), c.byref(n)), 1)
        self.assertEqual(bytes(out[10:n.value]), bytes.fromhex('9000'))



for _name in list(vars(transport.TransportTests)):
    if _name.startswith('test_'):
        setattr(ClassicBridgeTests, _name, None)
