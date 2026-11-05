/* SPDX-License-Identifier: Apache-2.0 */
#ifndef PAKURI_TIMING_H
#define PAKURI_TIMING_H
#ifdef MG_TIMING
#include "memory.h"
#include "ch552_regs.h"
extern __data uint16_t timing_loop_max;
extern volatile __data uint8_t timing_irq_max;
extern volatile __bit timing_uart_overflow;
void timing_init(void);
void timing_poll(void);
#if defined(CH552_HOST_TEST) && !defined(TIMING_BOOKEND_HOOK)
#define TIMING_BOOKEND_HOOK() ((void)0)
#endif
#define TIMING_IRQ_SAMPLE() do { \
    uint8_t late = TL0; \
    if (TH0) late = 255; \
    if (late > timing_irq_max) timing_irq_max = late; \
} while (0)
#define TIMING_UART_OVERFLOW() (timing_uart_overflow = 1)
#else
#define timing_init() ((void)0)
#define timing_poll() ((void)0)
#define TIMING_IRQ_SAMPLE() ((void)0)
#define TIMING_UART_OVERFLOW() ((void)0)
#endif
#endif
