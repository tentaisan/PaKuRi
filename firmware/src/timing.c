/* SPDX-License-Identifier: Apache-2.0 */
#include "timing.h"
#ifdef MG_TIMING
__data uint16_t timing_loop_max;
volatile __data uint8_t timing_irq_max;
volatile __bit timing_uart_overflow;

void timing_init(void) {
    T2CON = 0;
    T2MOD &= 0xb0;
    RCAP2H = RCAP2L = TH2 = TL2 = 0;
    timing_loop_max = 0; timing_irq_max = timing_uart_overflow = 0;
    TR2 = 1;
}

void timing_poll(void) {
    union { uint16_t count; uint8_t byte[2]; } elapsed;
    uint8_t before;
    __bit enabled = EA;


    EA = 0; before = TL0; TR2 = 0;
#ifdef CH552_HOST_TEST
    TIMING_BOOKEND_HOOK();
#endif
    if (TF2) elapsed.count = 0xffff;
    else { elapsed.byte[0] = TL2; elapsed.byte[1] = TH2; }
    TF2 = 0; TH2 = TL2 = 0;
    TR2 = 1;
    before = (uint8_t)(TL0 - before);
    EA = enabled;


    if (elapsed.byte[1] >= 254) elapsed.count = 0xffff;
    else elapsed.count += (uint16_t)before + 2;
    if (elapsed.count > timing_loop_max) timing_loop_max = elapsed.count;
}
#endif
