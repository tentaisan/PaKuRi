/* SPDX-License-Identifier: AGPL-3.0-only */

#define CH552_HOST_TEST
#define CH552_DEFINE_REGISTERS
#include "../src/uart.c"
#include <assert.h>
#include <string.h>

int main(int argc, char **argv) {
    uint8_t byte = 0, i;
    assert(argc == 2);
    T2CON = 0xff;
#ifdef MG_CH559
    P0_DIR = 0xff; P0_PU = 0; PIN_FUNC = 0; PORT_CFG = 0;
#else
    P3_DIR_PU = P3_MOD_OC = 0xff;
#endif
    uart_init();
    if (!strcmp(argv[1], "init")) {
        assert(TH1 == 243 && TL1 == 243 && SCON == 0x50);
        assert((T2CON & 0x30) == 0 && ES == 1 && TR1 == 1);
#ifdef MG_CH559
        assert((P0_DIR & 0x0c) == 0x08 && (P0_PU & 0x0c) == 0x0c);
        assert((PIN_FUNC & 0x10) && (PORT_CFG & 1));
#else
        assert((P3_DIR_PU & 3) == 2 && (P3_MOD_OC & 3) == 0);
#endif
    } else if (!strcmp(argv[1], "rx")) {
        for (i = 0; i < 63; ++i) { SBUF = i; RI = 1; serial_interrupt(); }
        for (i = 0; i < 63; ++i) { assert(uart_receive(&byte) && byte == i); }
        assert(!uart_receive(&byte) && !uart_faulted());
        for (i = 0; i < 100; ++i) {
            SBUF = i; RI = 1; serial_interrupt();
            assert(uart_receive(&byte) && byte == i);
        }
    } else if (!strcmp(argv[1], "overflow")) {
        for (i = 0; i < 64; ++i) { SBUF = i; RI = 1; serial_interrupt(); }
        assert(uart_faulted() && !uart_receive(&byte) && !uart_transmit(1));
        EA = 1; uart_reset();
        assert(EA == 1 && !uart_faulted() && !uart_receive(&byte));
        SBUF = 0x55; RI = 1; serial_interrupt();
        assert(uart_receive(&byte) && byte == 0x55);
    } else if (!strcmp(argv[1], "tx")) {
        assert(uart_transmit(0x12) && SBUF == 0x12);
        assert(!uart_transmit(0x34) && SBUF == 0x12);
        TI = 1; RI = 0; serial_interrupt();
        assert(uart_transmit(0x34) && SBUF == 0x34);
        uart_stop();
        assert(!ES && !TR1 && !(SCON & 0x10));
        assert(!uart_transmit(0x56) && !uart_receive(&byte));
    } else {
        assert(0);
    }
    return 0;
}
