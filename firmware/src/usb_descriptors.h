/* SPDX-License-Identifier: AGPL-3.0-only */
/* ManeKey usb_descriptors.hから2026-10-25改変。CCID専用・短APDU・1slot。 */
#ifndef PAKURI_USB_DESCRIPTORS_H
#define PAKURI_USB_DESCRIPTORS_H
#ifndef __SDCC
#define __code
#endif

static const __code unsigned char device_descriptor[] = {
    18,1,0,2,0,0,0,64,0xfe,0xca,0x22,0x55,0,1,0,0,0,1
};
static const __code unsigned char configuration_descriptor[] = {
    9,2,93,0,1,1,0,0x80,250,
    9,4,0,0,3,0x0b,0,0,0,


    54,0x21,0x10,1,0,1,2,0,0,0,
    0xa0,0x0f,0,0,0xa0,0x0f,0,0,1,
    0x80,0x25,0,0,0x80,0x25,0,0,1,
    0xfe,0,0,0,0,0,0,0,0,0,0,0,
    0x42,4,2,0,0x0f,1,0,0,0xff,0xff,0,0,0,1,
    7,5,0x82,2,64,0,0,
    7,5,0x02,2,64,0,0,

    7,5,0x81,3,8,0,16
};
static const __code unsigned char clock_frequency[] = {0xa0,0x0f,0,0};
static const __code unsigned char data_rate[] = {0x80,0x25,0,0};
#endif
