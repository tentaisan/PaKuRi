# SPDX-License-Identifier: Apache-2.0
"""通常40h経路のRF待ち設定候補。既存のA/B・取消・期限・復旧を同じ実Cで回帰。"""
import test_reader as reader
import test_gate as gate


class AutoWaitReaderTests(reader.ReaderTests):
    singleton=True
    extra_flags=('-DMG_RF_WAIT',)

    def initialize(self):
        for payload in (reader.VERSION,b'',b'',b'',b''):self.respond(payload)
        self.assertEqual((self.r.phase,self.r.initialized),(reader.R_DONE,1))
        self.release()

    def test_rf_wait_and_retry_configuration_are_both_required(self):
        self.initialize();wire=self.sent()
        self.assertLess(wire.index(bytes.fromhex('d43202000b0d')),wire.index(bytes.fromhex('d43205000000')))
        self.setUp()
        for payload in (reader.VERSION,b'',b''):self.respond(payload)
        self.assertEqual(self.r.phase,13)
        self.respond(b'\0')
        self.assertEqual((self.r.phase,self.r.initialized),(reader.R_FAILED,0))


class AutoWaitGateTests(gate.GateTests):
    extra_flags=('-DMG_RF_WAIT',)

    def initialize(self):
        for payload in (gate.VERSION,b'',b'',b'',b''):self.respond(payload)
        self.assertEqual(self.r.initialized,1)

    def test_full_command_and_response_keep_automatic_path_for_both_families(self):
        for family in (0,3):
            with self.subTest(family=family):
                self.setUp();self.initialize();self.power_on(family)
                before=len(self.sent())
                request=bytes((0,0xa4,4,0,255))+bytes(range(256))
                self.send(gate.command(0x6f,request,sequence=93))
                data=bytes(range(256))+b'\x90\0'
                self.respond(b'\0'+data)
                reply,sizes=self.final()
                self.assertIn(b'\xd4\x40\x01'+request,self.sent()[before:])
                self.assertEqual(reply[10:],data)
                self.assertEqual(sizes,[64,64,64,64,12])
