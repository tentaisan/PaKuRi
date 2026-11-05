/* SPDX-License-Identifier: AGPL-3.0-only */

#ifndef PAKURI_CH559_REGS_H
#define PAKURI_CH559_REGS_H
#include <stdint.h>
#ifndef MG_CH559
#error CH559 register definitions require the isolated CH559 target
#endif
#ifdef CH552_HOST_TEST
#define __bit uint8_t
#define __at(addr)
#define __interrupt(number)
#define __using(bank)
#ifdef CH552_DEFINE_REGISTERS
#define SFR(name, addr) volatile uint8_t name
#define SBIT(name, addr) volatile uint8_t name
volatile uint8_t ch559_xsfr_mock[0x50];
#else
#define SFR(name, addr) extern volatile uint8_t name
#define SBIT(name, addr) extern volatile uint8_t name
extern volatile uint8_t ch559_xsfr_mock[0x50];
#endif
#define XSFR(addr) (ch559_xsfr_mock[(addr) - 0x2400])
#else
#define SFR(name, addr) __sfr __at(addr) name
#define SBIT(name, addr) __sbit __at(addr) name
#define XSFR(addr) (*((volatile __xdata uint8_t *)(addr)))
#endif
SFR(SP,0x81); SFR(IE,0xa8); SFR(IE_EX,0xe8); SFR(IP,0xb8);
SFR(SAFE_MOD,0xa1); SFR(PLL_CFG,0xb2); SFR(CLOCK_CFG,0xb3);
SFR(TMOD,0x89); SFR(TCON,0x88); SFR(TL0,0x8a); SFR(TH0,0x8c);
SFR(TL1,0x8b); SFR(TH1,0x8d); SFR(T2CON,0xc8); SFR(T2MOD,0xc9);
SFR(SCON,0x98); SFR(SBUF,0x99); SFR(PCON,0x87);
SFR(P0,0x80); SFR(P0_DIR,0xc4); SFR(P0_PU,0xc5); SFR(PORT_CFG,0xc6); SFR(PIN_FUNC,0xce);
SFR(USB_RX_LEN,0xd1); SFR(UEP1_CTRL,0xd2); SFR(UEP1_T_LEN,0xd3);
SFR(UEP2_CTRL,0xd4); SFR(UEP2_T_LEN,0xd5); SFR(USB_INT_FG,0xd8);
SFR(USB_INT_ST,0xd9); SFR(USB_MIS_ST,0xda); SFR(UEP0_CTRL,0xdc);
SFR(UEP0_T_LEN,0xdd); SFR(USB_INT_EN,0xe1); SFR(USB_CTRL,0xe2);
SFR(USB_DEV_AD,0xe3); SFR(UDEV_CTRL,0xe4);
#define UEP4_1_MOD XSFR(0x2446)
#define UEP2_3_MOD XSFR(0x2447)
#define UEP0_DMA_H XSFR(0x2448)
#define UEP0_DMA_L XSFR(0x2449)
#define UEP1_DMA_H XSFR(0x244a)
#define UEP1_DMA_L XSFR(0x244b)
#define UEP2_DMA_H XSFR(0x244c)
#define UEP2_DMA_L XSFR(0x244d)
SBIT(UIF_BUS_RST,0xd8); SBIT(UIF_TRANSFER,0xd9);
SBIT(EA,0xaf); SBIT(ES,0xac); SBIT(TR1,0x8e); SBIT(ET0,0xa9);
SBIT(TR0,0x8c); SBIT(TF0,0x8d); SBIT(RI,0x98); SBIT(TI,0x99);
#endif
