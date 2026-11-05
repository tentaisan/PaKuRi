/* SPDX-License-Identifier: AGPL-3.0-only */
/* ManeKey usb_bridge.cのclock/timer/初期化順序から2026-10-25改変。
 * PaKuRi CCID専用。bootloader/Config/DataFlashへ書く処理は持たない。 */
#include "gate.h"
#include "uart.h"
#ifdef MG_CH559
#include "../ch559/ch559_regs.h"
#else
#include "ch552_regs.h"
#endif
#include "timing.h"
#ifdef MG_STANDALONE_OBSERVER
#include "../experimental/standalone/state.h"
#endif
#ifdef MG_STANDALONE_DISPATCH
#include "../experimental/standalone/dispatch.h"
#endif

#ifdef MG_RESET_DIAGNOSTIC
volatile __data uint16_t milliseconds;
#else
static volatile __data uint16_t milliseconds;
#endif
#ifdef MG_CLASSIC_CALL_PROBE
void classic_probe_call(void);
#endif
void timer0_interrupt(void) __interrupt(1) __using(2) {
    TIMING_IRQ_SAMPLE();
    TH0 = 0xf8; TL0 = 0x30;
    ++milliseconds;
}
void main(void) {
    uint16_t __data now, delay;
    uint8_t __data paint;
    EA = 0; IE = IE_EX = IP = 0; USB_CTRL = 0; UDEV_CTRL = 0;
    TR0 = TF0 = 0;
    paint = SP;
    while (++paint) *((volatile uint8_t __idata *)paint) = 0xa5;
#ifdef MG_CH559


    SAFE_MOD = 0x55; SAFE_MOD = 0xaa; PLL_CFG = 0xd8; SAFE_MOD = 0;
    for (delay = 0; delay < 50000; ++delay) __asm nop __endasm;
    SAFE_MOD = 0x55; SAFE_MOD = 0xaa; CLOCK_CFG = 0x8c; SAFE_MOD = 0;
#else
    SAFE_MOD = 0x55; SAFE_MOD = 0xaa; CLOCK_CFG = 0x86; SAFE_MOD = 0;
#endif
    for (delay = 0; delay < 50000; ++delay) __asm nop __endasm;
    TMOD = (TMOD & 0xf0) | 1; T2MOD &= ~0x10;
    TH0 = 0xf8; TL0 = 0x30; milliseconds = 0;
#ifdef MG_CLASSIC_CALL_PROBE

    classic_probe_call();
#endif
    uart_init(); gate_init(0); usb_device_init();
#ifdef MG_STANDALONE_OBSERVER
    mg_standalone_init();
#endif
    timing_init();
    ET0 = 1; TR0 = 1; EA = 1;
    for (;;) {
        timing_poll();
        EA = 0; now = milliseconds; EA = 1;
        usb_device_poll(); gate_poll(now);
#ifdef MG_STANDALONE_OBSERVER
        mg_standalone_poll();
#endif
#ifdef MG_STANDALONE_DISPATCH
        mg_dispatch_poll();
#endif
    }
}
