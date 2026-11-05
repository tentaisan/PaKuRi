/* SPDX-License-Identifier: AGPL-3.0-only */

#include "memory.h"
#ifdef MG_CH559
#include "../ch559/ch559_regs.h"
#else
#include "ch552_regs.h"
#endif
#include "uart.h"
#include "timing.h"

static volatile __xdata uint8_t uart_rx[64];
static volatile __data uint8_t rx_head, rx_tail, rx_fault, tx_ready;

void serial_interrupt(void) __interrupt(4) __using(1) {
    uint8_t next;
    if (RI) {
        RI = 0;
        next = (rx_head + 1) & 63;
        if (next == rx_tail) { rx_fault = 1; TIMING_UART_OVERFLOW(); (void)SBUF; }
        else { uart_rx[rx_head] = SBUF; rx_head = next; }
    }
    if (TI) { TI = 0; tx_ready = 1; }
}

void uart_reset(void) {
    uint8_t was_enabled = EA;
    EA = 0;
    rx_head = rx_tail = rx_fault = 0;
    EA = was_enabled;
}

void uart_init(void) {

    ES = 0;
    TR1 = 0;


#ifdef MG_CH559

    PIN_FUNC |= 0x10; P0 |= 0x0c; PORT_CFG |= 0x01;
    P0_DIR = (P0_DIR & (uint8_t)~0x04) | 0x08;
    P0_PU |= 0x0c;
#else
    PIN_FUNC &= ~0x10;
    P3 |= 3;
    P3_DIR_PU &= ~3;
    P3_MOD_OC &= ~3;
    P3_DIR_PU |= 2;
#endif
    TMOD = (TMOD & 0x0f) | 0x20;


    T2CON &= ~0x30;
    T2MOD |= 0xa0; PCON |= 0x80;
    TH1 = TL1 = 243; SCON = 0x50; TR1 = 1; tx_ready = 1;
    uart_reset();
    ES = 1;
}

uint8_t uart_receive(uint8_t __data *byte) {
    if (!ES || rx_fault || rx_tail == rx_head) return 0;
    *byte = uart_rx[rx_tail];
    rx_tail = (rx_tail + 1) & 63;
    return 1;
}

uint8_t uart_transmit(uint8_t byte) {
    if (!ES || rx_fault || !tx_ready) return 0;
    tx_ready = 0; SBUF = byte;
    return 1;
}

uint8_t uart_faulted(void) { return rx_fault; }
uint8_t uart_tx_idle(void) { return tx_ready; }

void uart_stop(void) {
    ES = 0; TR1 = 0; SCON &= ~0x10;
}
