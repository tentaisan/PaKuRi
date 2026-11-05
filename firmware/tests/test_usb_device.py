# SPDX-License-Identifier: AGPL-3.0-only
"""実C USB/EP0をmock SFRで検査。実バス・DMA timingの保証は含まない。"""
import ctypes as c
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest


class UsbDeviceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="pakuri-usb-")
        cls.addClassCleanup(cls.tmp.cleanup)
        out = Path(cls.tmp.name) / "usb.so"
        source = Path(__file__).with_name("usb_harness.c")
        subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-shared",
                        "-fPIC", "-fsanitize=undefined", "-fno-sanitize-recover=all",
                        *getattr(cls, 'extra_flags', ()),
                        str(source), "-o", str(out)], check=True)
        cls.lib = c.CDLL(str(out))
        cls.lib.test_transfer.argtypes = [c.c_uint8, c.c_uint8]
        cls.lib.usb_send_bulk.argtypes = [c.c_uint8]
        cls.lib.usb_send_bulk.restype = c.c_uint8
        cls.lib.usb_bulk_ready.restype = c.c_uint8
        cls.lib.usb_notify_slot.argtypes = [c.c_uint8]
        cls.lib.test_queue_setup.argtypes = [c.POINTER(c.c_uint8)]

    def setUp(self):
        self.lib.test_usb_init()
        self.ep0 = (c.c_uint8 * 64).in_dll(self.lib, "usb_ep0")
        self.ep1 = (c.c_uint8 * 64).in_dll(self.lib, "usb_ep1")
        self.ep2 = (c.c_uint8 * 128).in_dll(self.lib, "usb_ep2")

    def get(self, name):
        return c.c_uint8.in_dll(self.lib, name).value

    def put(self, name, value):
        c.c_uint8.in_dll(self.lib, name).value = value

    def setup(self, kind, request, value=0, index=0, length=0):
        data = struct.pack("<BBHHH", kind, request, value, index, length)
        self.ep0[:8] = data
        self.lib.test_transfer(0x30, 8)

    def configured(self):
        self.setup(0, 9, 1)
        self.assertEqual(self.get("usb_configured"), 0)
        self.lib.test_transfer(0x20, 0)
        self.assertEqual(self.get("usb_configured"), 1)
        self.put("usb_events", 0)

    def read_descriptor(self, value, length=255, kind=0x80):
        self.setup(kind, 6, value, length=length)
        result = bytearray()
        while True:
            count = self.get("UEP0_T_LEN")
            result += bytes(self.ep0)[:count]
            self.lib.test_transfer(0x20, 0)
            if self.get("UEP0_CTRL") & 3 == 2:
                break
        self.lib.test_transfer(0x40, 0)
        return bytes(result)

    def test_descriptor_contract_and_packet_splitting(self):
        device = self.read_descriptor(0x100)
        self.assertEqual(len(device), 18)
        self.assertEqual(struct.unpack_from("<HH", device, 8), (0xCAFE, 0x5522))
        config = self.read_descriptor(0x200)
        self.assertEqual(len(config), 93)
        self.assertEqual(struct.unpack_from("<H", config, 2)[0], len(config))
        descriptors, at = [], 0
        while at < len(config):
            size = config[at]
            self.assertGreaterEqual(size, 2)
            descriptors.append(config[at:at + size]); at += size
        self.assertEqual([len(d) for d in descriptors], [9, 9, 54, 7, 7, 7])
        self.assertEqual(config[4], 1)
        self.assertEqual(descriptors[1][4:7], bytes([3, 0x0B, 0]))
        ccid = descriptors[2]
        self.assertEqual(ccid[4], 0)
        self.assertEqual(struct.unpack_from("<I", ccid, 6)[0], 2)
        self.assertEqual(struct.unpack_from("<I", ccid, 40)[0], 0x20442)
        self.assertEqual(struct.unpack_from("<I", ccid, 44)[0], 271)
        self.assertEqual(ccid[52:54], bytes([0, 1]))
        self.assertEqual([(d[2], d[3], struct.unpack_from("<H", d, 4)[0])
                          for d in descriptors[3:]], [(0x82, 2, 64), (2, 2, 64), (0x81, 3, 8)])
        self.assertEqual(self.read_descriptor(0x2100, kind=0x81), ccid)
        self.assertEqual(self.read_descriptor(0x200, length=9), config[:9])

    def test_address_and_configuration_commit_on_status_completion(self):
        self.setup(0, 5, 37)
        self.assertEqual(self.get("USB_DEV_AD"), 0)
        self.lib.test_transfer(0x20, 0)
        self.assertEqual(self.get("USB_DEV_AD"), 37)
        self.configured()
        self.setup(0x80, 8, length=1)
        self.assertEqual(self.ep0[0], 1)
        self.setup(0, 9, 0)
        self.assertEqual(self.get("usb_configured"), 1)
        self.lib.test_transfer(0x20, 0)
        self.assertEqual(self.get("usb_configured"), 0)
        self.assertEqual(self.get("usb_events"), 1)

    def test_new_setup_cancels_pending_address(self):
        self.setup(0, 5, 27)
        self.setup(0x80, 6, 0x100, length=18)
        self.lib.test_transfer(0x20, 0)
        self.assertEqual(self.get("USB_DEV_AD"), 0)

    def test_reject_unimplemented_or_malformed_requests(self):
        self.configured()
        for arguments in ((0, 5, 128), (0, 9, 2), (0x80, 6, 0x300),
                          (0x21, 9), (0x21, 10), (0x81, 6, 0x2200),
                          (0x81, 10, 0, 1, 1), (1, 11, 1), (2, 3, 0, 0x12)):
            with self.subTest(arguments=arguments):
                self.setup(*arguments)
                self.assertEqual(self.get("UEP0_CTRL"), 0x0F)
        self.lib.test_transfer(0x30, 7)
        self.assertEqual(self.get("UEP0_CTRL"), 0x0F)

    def test_class_clock_rate_and_abort_tuple(self):
        self.configured()
        for request, expected in ((2, 4000), (3, 9600)):
            self.setup(0xA1, request, length=4)
            self.assertEqual(self.get("UEP0_T_LEN"), 4)
            self.assertEqual(int.from_bytes(bytes(self.ep0[:4]), "little"), expected)
        self.setup(0x21, 1, 0x2300)
        self.assertEqual((self.get("usb_abort_pending"), self.get("usb_abort_sequence")), (1, 0x23))
        self.assertEqual(self.get("usb_events") & 8, 8)
        self.assertEqual(self.lib.usb_send_bulk(10), 0)
        self.setup(0x21, 1, 0x2400)
        self.assertEqual(self.get("UEP0_CTRL"), 0x0F)
        self.assertEqual(self.get("usb_abort_sequence"), 0x23)
        self.lib.usb_abort_complete()
        self.assertEqual(self.lib.usb_send_bulk(10), 1)

    def test_duplicate_out_and_retained_dma_ownership(self):
        self.configured(); self.lib.usb_device_arm()
        toggle = self.get("UEP2_CTRL") & 0x80
        self.ep2[:4] = b"test"
        self.lib.test_transfer(2, 4)
        self.assertEqual(self.get("usb_out_pending"), 0)
        self.assertEqual(self.get("UEP2_CTRL") & 0x80, toggle)
        self.lib.test_transfer(0x42, 4)
        self.assertEqual((self.get("usb_out_pending"), self.get("usb_out_length")), (1, 4))
        self.assertEqual(self.get("UEP2_CTRL") & 0x80, toggle ^ 0x80)
        self.lib.usb_device_arm()
        self.assertEqual(self.get("UEP2_CTRL") & 12, 8)
        self.assertEqual(bytes(self.ep2[:4]), b"test")
        self.lib.usb_release_out()
        self.assertEqual(bytes(self.ep2[:64]), bytes(64))
        self.lib.usb_device_arm()
        self.assertEqual(self.get("UEP2_CTRL") & 12, 0)

    def test_bulk_in_completion_preserves_new_setup(self):
        self.configured()
        self.assertEqual(self.lib.usb_send_bulk(64), 1)
        self.assertEqual(self.lib.usb_send_bulk(10), 0)
        self.lib.usb_device_arm()
        setup = (c.c_uint8 * 8).from_buffer_copy(struct.pack("<BBHHH", 0x21, 1, 0x4200, 0, 0))
        self.lib.test_queue_setup(setup)
        self.lib.test_transfer(0x22, 0)
        self.assertEqual(self.get("USB_INT_FG") & 2, 2)
        self.assertEqual(self.get("usb_events") & 4, 4)
        self.lib.usb_device_poll()
        self.assertEqual((self.get("usb_abort_pending"), self.get("usb_abort_sequence")), (1, 0x42))

    def test_notification_buffer_not_overwritten_until_completion(self):
        self.configured(); self.lib.usb_device_arm()
        self.assertEqual(bytes(self.ep1[:2]), b"\x50\x02")
        self.lib.usb_notify_slot(1); self.lib.usb_device_arm()
        self.assertEqual(bytes(self.ep1[:2]), b"\x50\x02")
        self.lib.test_transfer(0x21, 0); self.lib.usb_device_arm()
        self.assertEqual(bytes(self.ep1[:2]), b"\x50\x03")

    def test_each_notification_completes_libccid_eight_byte_interrupt_read(self):


        config = self.read_descriptor(0x200)
        packet_limit = struct.unpack_from('<H', config, len(config) - 3)[0]
        self.configured()
        for present in (0, 1, 0, 1):
            self.lib.usb_notify_slot(present)
            self.lib.usb_device_arm()
            length = self.get('UEP1_T_LEN')
            self.assertEqual(bytes(self.ep1[:length]), bytes((0x50, 2 | present)))
            self.assertTrue(length == 8 or length < packet_limit,
                            'one notification does not finish libccid interrupt read')
            self.lib.test_transfer(0x21, 0)

    def test_bus_reset_drops_ownership_and_reports_cancellation(self):
        self.configured(); self.lib.usb_send_bulk(10)
        self.lib.test_transfer(0x42, 64)
        self.lib.test_reset()
        self.assertEqual(self.get("usb_configured"), 0)
        self.assertEqual(self.get("usb_in_armed"), 0)
        self.assertEqual(self.get("usb_out_pending"), 0)
        self.assertEqual(self.get("usb_events"), 1)
        self.assertEqual(bytes(self.ep2), bytes(128))

    def test_halt_and_fault_cannot_be_rearmed_by_clearing_events(self):
        self.configured(); self.setup(2, 3, index=0x82)
        self.lib.usb_device_arm()
        self.assertEqual(self.get("UEP2_CTRL") & 3, 3)
        self.setup(0x82, 0, index=0x82, length=2)
        self.assertEqual(self.ep0[0], 1)
        self.setup(2, 1, index=0x82)
        self.assertEqual(self.lib.usb_bulk_ready(), 1)
        self.assertEqual(self.get("usb_events"), 1)
        self.put("USB_INT_FG", 0x10); self.lib.usb_device_poll()
        self.assertEqual(self.get("usb_events") & 16, 16)
        self.put("usb_events", 0); self.lib.usb_device_arm()
        self.assertEqual(self.lib.usb_bulk_ready(), 0)
        self.assertEqual(self.get("UEP2_CTRL"), 0x0A)

    def test_clear_halt_preserves_other_direction_toggle_and_halt(self):
        self.configured()
        self.setup(2, 3, index=2)
        self.setup(2, 3, index=0x82)
        self.put("UEP2_CTRL", 0xCF)
        self.setup(2, 1, index=0x82)
        self.assertEqual(self.get("UEP2_CTRL") & 0xC0, 0x80)
        self.lib.usb_device_arm()
        self.assertEqual(self.get("UEP2_CTRL") & 12, 12)
        self.put("UEP2_CTRL", 0xCA)
        self.setup(2, 1, index=2)
        self.assertEqual(self.get("UEP2_CTRL") & 0xC0, 0x40)
        self.lib.usb_device_arm()
        self.assertEqual(self.get("UEP2_CTRL") & 12, 0)

    def test_read_only_stack_observation_and_strict_tuple(self):
        ram = (c.c_uint8 * 256).in_dll(self.lib, "usb_test_iram")
        ram[:] = bytes([0xA5]) * 256
        self.setup(0xC0, 0x5B, length=2)
        self.assertEqual(bytes(self.ep0[:2]), b"\x44\x00")
        ram[0x43] = 0
        ram[0x44] = 0
        ram[0x8C] = 0
        snapshot = bytes(ram)
        self.setup(0xC0, 0x5B, length=2)
        self.assertEqual(bytes(self.ep0[:2]), b"\x44\x8c")
        self.assertEqual(bytes(ram), snapshot)
        self.lib.test_reset()
        self.setup(0xC0, 0x5B, length=2)
        self.assertEqual(bytes(self.ep0[:2]), b"\x44\x8c")
        ram[255] = 0
        self.setup(0xC0, 0x5B, length=2)
        self.assertEqual(bytes(self.ep0[:2]), b"\x44\xff")
        for args in ((0x40, 0x5B, 0, 0, 2), (0xC1, 0x5B, 0, 0, 2),
                     (0xC0, 0x5B, 1, 0, 2), (0xC0, 0x5B, 0, 1, 2),
                     (0xC0, 0x5B, 0, 0, 1), (0xC0, 0x5B, 0x100, 0, 2),
                     (0xC0, 0x5B, 0, 0x100, 2), (0xC0, 0x5B, 0, 0, 258)):
            self.setup(*args)
            self.assertEqual(self.get("UEP0_CTRL"), 0x0F)


    def test_reader_diagnostic_is_fixed_read_only_status(self):
        self.lib.test_reader_diagnostic(12, 5, 33, 1)
        self.setup(0xC0, 0x5C, length=4)
        self.assertEqual(bytes(self.ep0[:4]), bytes([12, 5, 33, 1]))
        self.assertEqual(self.get("UEP0_T_LEN"), 4)
        for args in ((0x40, 0x5C, 0, 0, 4), (0xC1, 0x5C, 0, 0, 4),
                     (0xC0, 0x5C, 1, 0, 4), (0xC0, 0x5C, 0, 1, 4),
                     (0xC0, 0x5C, 0x100, 0, 4), (0xC0, 0x5C, 0, 0x100, 4),
                     (0xC0, 0x5C, 0, 0, 3), (0xC0, 0x5C, 0, 0, 260)):
            self.setup(*args)
            self.assertEqual(self.get("UEP0_CTRL"), 0x0F)
        self.setup(0xC0, 0x5C, length=4)
        self.assertEqual(bytes(self.ep0[:4]), bytes([12, 5, 33, 1]))


    def test_reader_diagnostic_length_extension_is_metadata_only(self):
        from test_reader import Reader
        reader = Reader.in_dll(self.lib, 'reader_state')
        reader.phase = 12; reader.error = 2; reader.pn.error = 0
        reader.rf_status = 0x12; reader.pn.payload = 259
        reader.pn.frame[:] = bytes([0x5a]) * len(reader.pn.frame)
        snapshot = bytes(reader)
        self.setup(0xC0, 0x5C, length=6)
        self.assertEqual(self.get('UEP0_T_LEN'), 6)
        self.assertEqual(bytes(self.ep0[:6]), bytes([12, 2, 0, 0x12, 3, 1]))
        self.assertEqual(bytes(reader), snapshot)
        for length in (0, 3, 5, 7, 262):
            self.setup(0xC0, 0x5C, length=length)
            self.assertEqual(self.get('UEP0_CTRL'), 0x0F)
        self.setup(0xC0, 0x5C, length=4)
        self.assertEqual(bytes(self.ep0[:4]), bytes([12, 2, 0, 0x12]))

    def test_abort_snapshot_is_fixed_read_only_and_reset_clears_it(self):
        snapshot = (c.c_uint8 * 3).in_dll(self.lib, 'usb_abort_snapshot')
        self.assertEqual(bytes(snapshot), b'\xff' * 3)

        snapshot[:] = bytes((7, 9, 5))
        events = self.get('usb_events')
        self.setup(0xC0, 0x5D, length=3)
        self.assertEqual((self.get('UEP0_T_LEN'), bytes(self.ep0[:3])), (3, bytes(snapshot)))
        self.assertEqual(self.get('usb_events'), events)
        for args in ((0x40, 0x5D, 0, 0, 3), (0xC1, 0x5D, 0, 0, 3),
                     (0xC0, 0x5D, 1, 0, 3), (0xC0, 0x5D, 0, 1, 3),
                     (0xC0, 0x5D, 0x100, 0, 3), (0xC0, 0x5D, 0, 0x100, 3),
                     (0xC0, 0x5D, 0, 0, 2), (0xC0, 0x5D, 0, 0, 259)):
            self.setup(*args)
            self.assertEqual(self.get('UEP0_CTRL'), 0x0F)
            self.assertEqual(bytes(snapshot), bytes((7, 9, 5)))
        self.lib.test_reset()
        self.assertEqual(bytes(snapshot), b'\xff' * 3)

    def test_selected_card_family_is_fixed_metadata_only(self):

        from test_reader import Reader
        reader = Reader.in_dll(self.lib, 'reader_state')
        reader.selected = 0; reader.card.type = 3
        self.setup(0xC0, 0x5E, length=1)
        self.assertEqual(bytes(self.ep0[:1]), b'\xff')
        for family in (0, 3):
            reader.selected = 1; reader.card.type = family
            self.setup(0xC0, 0x5E, length=1)
            self.assertEqual((self.get('UEP0_T_LEN'), self.ep0[0]), (1, family))
        for args in ((0x40, 0x5E, 0, 0, 1), (0xC1, 0x5E, 0, 0, 1),
                     (0xC0, 0x5E, 1, 0, 1), (0xC0, 0x5E, 0, 1, 1),
                     (0xC0, 0x5E, 0x100, 0, 1), (0xC0, 0x5E, 0, 0x100, 1),
                     (0xC0, 0x5E, 0, 0, 0), (0xC0, 0x5E, 0, 0, 257)):
            self.setup(*args)
            self.assertEqual(self.get('UEP0_CTRL'), 0x0F)

if __name__ == "__main__":
    unittest.main()
