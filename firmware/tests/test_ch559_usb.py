# SPDX-License-Identifier: Apache-2.0
"""CH559-target USB logic with mock SFR/xSFR; not hardware validation."""
import ctypes as c
import test_usb_device as usb


class Ch559UsbTests(usb.UsbDeviceTests):
    extra_flags = ('-DMG_CH559',)

    def test_ch559_endpoint_dma_and_device_mode_registers(self):
        regs = (c.c_uint8 * 0x50).in_dll(self.lib, 'ch559_xsfr_mock')
        self.assertEqual(regs[0x46:0x4e], [0x40, 0x0c, 0, 0, 0, 0x40, 0, 0x80])
        self.assertEqual(self.get('UDEV_CTRL'), 0x31)
        self.assertEqual(self.get('USB_CTRL'), 0x29)

    def test_reset_diagnostic_is_absent_without_opt_in(self):
        for length in (1, 3):
            self.setup(0xc0, 0x60, length=length)
            self.assertEqual(self.get('UEP0_CTRL'), 0x0f)
