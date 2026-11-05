/* SPDX-License-Identifier: AGPL-3.0-only */

#define CH552_HOST_TEST
#define CH552_DEFINE_REGISTERS
static void after_clear(void);
#define USB_AFTER_CLEAR() after_clear()
#include "../src/usb_device.c"
#ifdef MG_RESET_DIAGNOSTIC
volatile uint16_t milliseconds;
#endif
#ifdef MG_SCAN_DIAGNOSTIC
volatile uint8_t reader_scan_diagnostic[7];
#endif
#ifndef MG_SINGLETON
Reader reader_state;
#endif
void test_reader_diagnostic(uint8_t phase, uint8_t error, uint8_t pn_error, uint8_t status) {
    reader_state.phase = phase; reader_state.error = error;
    reader_state.pn.error = pn_error; reader_state.rf_status = status;
}
uint8_t usb_test_iram[256];
static uint8_t queued_setup[8], inject;
static void after_clear(void) {
    uint8_t i;
    if (!inject) return;
    inject = 0;
    for (i = 0; i < 8; ++i) usb_ep0[i] = queued_setup[i];
    USB_RX_LEN = 8; USB_INT_ST = 0x30; USB_INT_FG |= 2;
}
void test_queue_setup(const uint8_t *setup) {
    uint8_t i;
    for (i = 0; i < 8; ++i) queued_setup[i] = setup[i];
    inject = 1;
}
void test_usb_init(void) { inject = 0; USB_INT_FG = 0; usb_device_init(); }
void test_transfer(uint8_t state, uint8_t length) {
    USB_INT_ST = state; USB_RX_LEN = length; USB_INT_FG |= 2;
    usb_device_poll();
}
void test_reset(void) { USB_INT_FG |= 1; usb_device_poll(); }
