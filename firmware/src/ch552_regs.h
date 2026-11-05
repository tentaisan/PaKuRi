/* SPDX-License-Identifier: AGPL-3.0-only */

#ifndef PAKURI_CH552_REGS_H
#define PAKURI_CH552_REGS_H

#ifdef CH552_HOST_TEST
#define __data
#define __bit uint8_t
#define __at(addr)
#define __interrupt(number)
#define __using(bank)
#ifdef CH552_DEFINE_REGISTERS
#define SFR(name, addr) volatile uint8_t name
#define SBIT(name, addr) volatile uint8_t name
#else
#define SFR(name, addr) extern volatile uint8_t name
#define SBIT(name, addr) extern volatile uint8_t name
#endif
#else
#define SFR(name, addr) __sfr __at(addr) name
#define SBIT(name, addr) __sbit __at(addr) name
#endif
SFR(SP, 0x81);
SFR(IE, 0xa8); SFR(IE_EX, 0xe8); SFR(IP, 0xb8);
SFR(SAFE_MOD, 0xa1); SFR(CLOCK_CFG, 0xb9);
SFR(TMOD, 0x89); SFR(TCON, 0x88); SFR(TL0, 0x8a); SFR(TH0, 0x8c);
SFR(TL1, 0x8b); SFR(TH1, 0x8d); SFR(T2CON, 0xc8); SFR(T2MOD, 0xc9);
SFR(RCAP2L, 0xca); SFR(RCAP2H, 0xcb); SFR(TL2, 0xcc); SFR(TH2, 0xcd);
SFR(SCON, 0x98); SFR(SBUF, 0x99); SFR(PCON, 0x87);
SFR(P3, 0xb0); SFR(P3_MOD_OC, 0x96); SFR(P3_DIR_PU, 0x97); SFR(PIN_FUNC, 0xc6);
SFR(USB_CTRL, 0xe2); SFR(UDEV_CTRL, 0xd1); SFR(USB_DEV_AD, 0xe3);
SFR(USB_INT_EN, 0xe1); SFR(USB_INT_FG, 0xd8); SFR(USB_INT_ST, 0xd9);
SFR(USB_MIS_ST, 0xda); SFR(USB_RX_LEN, 0xdb); SFR(UEP0_CTRL, 0xdc); SFR(UEP0_T_LEN, 0xdd);
SFR(UEP1_CTRL, 0xd2); SFR(UEP1_T_LEN, 0xd3); SFR(UEP4_1_MOD, 0xea);
SFR(UEP2_3_MOD, 0xeb);


SFR(UEP2_CTRL, 0xd4); SFR(UEP2_T_LEN, 0xd5);
SFR(UEP2_DMA_L, 0xe4); SFR(UEP2_DMA_H, 0xe5);
SFR(UEP0_DMA_L, 0xec); SFR(UEP0_DMA_H, 0xed);
SFR(UEP1_DMA_L, 0xee); SFR(UEP1_DMA_H, 0xef);
SBIT(UIF_BUS_RST, 0xd8);
SBIT(UIF_TRANSFER, 0xd9);
SBIT(EA, 0xaf); SBIT(ES, 0xac); SBIT(TR1, 0x8e);
SBIT(ET0, 0xa9);
SBIT(TR0, 0x8c); SBIT(TF0, 0x8d); SBIT(RI, 0x98); SBIT(TI, 0x99);
SBIT(TR2, 0xca); SBIT(TF2, 0xcf);
#endif
