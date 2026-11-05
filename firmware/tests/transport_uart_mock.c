/* SPDX-License-Identifier: Apache-2.0 */

#include "../src/uart.h"
static uint8_t incoming[4096], outgoing[4096], idle = 1, fault;
static uint16_t rx_at, rx_end, tx_end;
void uart_init(void) { rx_at = rx_end = tx_end = fault = 0; idle = 1; }
void uart_reset(void) { rx_at = rx_end = fault = 0; }
uint8_t uart_receive(uint8_t *byte) {
    if (fault || rx_at == rx_end) return 0;
    *byte = incoming[rx_at++]; return 1;
}
uint8_t uart_transmit(uint8_t byte) {
    if (fault || !idle || tx_end == sizeof(outgoing)) return 0;
    outgoing[tx_end++] = byte; return 1;
}
uint8_t uart_tx_idle(void) { return idle; }
uint8_t uart_faulted(void) { return fault; }
void uart_stop(void) { idle = 0; }
void test_feed(uint8_t byte) {
    if (rx_end == sizeof(incoming)) fault = 1;
    else incoming[rx_end++] = byte;
}
uint16_t test_tx_length(void) { return tx_end; }
uint8_t test_tx_at(uint16_t at) { return outgoing[at]; }
void test_set_idle(uint8_t value) { idle = value; }
void test_set_fault(uint8_t value) { fault = value; }
