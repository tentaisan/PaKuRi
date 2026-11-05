/* SPDX-License-Identifier: AGPL-3.0-only */
/* Adapted from ManeKey link.h/link_irq.h, 2026-10-25. */
#ifndef PAKURI_UART_H
#define PAKURI_UART_H
#include "memory.h"
#ifdef __SDCC
void serial_interrupt(void) __interrupt(4) __using(1);
#endif

void uart_init(void);
void uart_reset(void);
uint8_t uart_receive(uint8_t __data *byte);
uint8_t uart_transmit(uint8_t byte);
uint8_t uart_faulted(void);

uint8_t uart_tx_idle(void);
void uart_stop(void);
#endif
