# SPDX-License-Identifier: Apache-2.0
"""検出情報だけを残す実C診断profile。UID非転送・不正応答・送信拒否を検査。"""
import ctypes as c
import unittest
import test_reader as reader
from test_pn532_frame import array
from test_card import type_a, type_b


class ScanDiagnosticTests(unittest.TestCase):
    singleton = True
    extra_flags = ('-DMG_SCAN_DIAGNOSTIC',)
    setUpClass = classmethod(reader.ReaderTests.setUpClass.__func__)
    setUp = reader.ReaderTests.setUp
    poll = reader.ReaderTests.poll
    respond = reader.ReaderTests.respond
    initialize = reader.ReaderTests.initialize
    release = reader.ReaderTests.release
    scan = reader.ReaderTests.scan
    sent = reader.ReaderTests.sent

    def snapshot(self):
        return bytes((c.c_uint8 * 7).in_dll(self.lib, 'reader_scan_diagnostic'))

    def test_unsupported_type_a_metadata_excludes_uid_and_tracks_absence(self):
        self.initialize()
        self.assertEqual(self.snapshot(), bytes([0,255,0,0,0,0,255]))

        self.scan(payload=bytes.fromhex('010100040804deadbeef'))
        self.assertEqual(self.snapshot(), bytes([2,2,0,4,8,4,255]))
        self.assertFalse(self.r.selected)
        self.release(); self.scan(payload=b'\0')
        self.assertEqual(self.snapshot(), bytes([4,1,0,0,0,0,255]))

    def test_iso_dep_and_type_b_results_do_not_expose_atr_or_pupi(self):
        self.initialize(); self.scan(payload=type_a())
        a=self.snapshot()
        self.assertEqual((a[1],a[4]&32,a[5]),(0,32,4))
        self.release();self.r.active=0
        self.scan(kind=3,payload=type_b())
        b=self.snapshot()
        self.assertEqual(b[1:6],a[1:6]);self.assertEqual(b[6],0)

    def test_malformed_response_clears_metadata_without_out_of_bounds_access(self):
        for payload in (b'',b'\1',bytes.fromhex('01010004080a'),bytes.fromhex('010100040804')):
            self.setUp();self.initialize();self.scan(payload=payload)
            self.assertEqual(self.snapshot()[1:6],bytes([3,0,0,0,0]))
            self.assertEqual(self.r.phase,reader.R_FAILED)

    def test_application_exchange_rejected_without_uart_output(self):
        self.initialize();self.scan();self.release()
        before=self.sent()
        for apdu in (bytes.fromhex('00a4040000'),bytes.fromhex('ff82000006ffffffffffff')):
            rc=self.lib.reader_exchange(c.byref(self.r),array(apdu),len(apdu),self.now)
            self.assertEqual(rc,3)
        self.assertEqual(self.sent(),before)


class ScanUsbTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import subprocess,tempfile
        from pathlib import Path
        cls.tmp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.tmp.cleanup)
        out=Path(cls.tmp.name)/'usb.so'
        subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-shared','-fPIC',
                        '-DMG_SCAN_DIAGNOSTIC','-fsanitize=undefined','-fno-sanitize-recover=all',
                        str(Path(__file__).with_name('usb_harness.c')),'-o',str(out)],check=True)
        cls.lib=c.CDLL(str(out))
        cls.lib.test_transfer.argtypes=[c.c_uint8,c.c_uint8]

    def test_ep0_exports_exact_metadata_only_and_rejects_wrong_length(self):
        import struct
        self.lib.test_usb_init()
        ep0=(c.c_uint8*64).in_dll(self.lib,'usb_ep0')
        diagnostic=(c.c_uint8*7).in_dll(self.lib,'reader_scan_diagnostic')
        diagnostic[:]=bytes([2,2,0,4,8,4,1])
        ep0[:8]=struct.pack('<BBHHH',0xc0,0x60,0,0,7)
        self.lib.test_transfer(0x30,8)
        self.assertEqual(c.c_uint8.in_dll(self.lib,'UEP0_T_LEN').value,7)
        self.assertEqual(bytes(ep0[:7]),bytes(diagnostic))
        ep0[:8]=struct.pack('<BBHHH',0xc0,0x60,0,0,8)
        self.lib.test_transfer(0x30,8)
        self.assertEqual(c.c_uint8.in_dll(self.lib,'UEP0_CTRL').value&3,3)
