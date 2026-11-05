/* SPDX-License-Identifier: AGPL-3.0-only */

#include "ccid_packet.h"
#include "pn532_frame.h"
#include "pn532_transport.h"
#include "uart.h"
#include "usb_device.h"
#include "reader.h"

#ifdef MG_SINGLETON
#define reader reader_state
#else
static __xdata Reader reader;
#endif
static __xdata uint8_t scratch[54];
static __xdata CcidRx rx;
static __xdata CcidTx tx;
static __xdata uint16_t total;
static __data uint8_t consumed, written, byte, result;

void main(void) {
    uart_init();
    usb_device_init();
    reader_init(&reader, 0);
    ccid_rx_init(&rx, 271);
    ccid_tx_init(&tx, 268, usb_ep2 + 64);

    for (;;) {
        usb_device_poll();
        usb_device_arm();
        result = ccid_rx_push(&rx, usb_ep2, 64, &consumed, scratch, &written);
        reader_poll(&reader, total++);
        if (reader.phase == READER_IDLE) {
            if ((result & 3) == 0) result |= reader_scan(&reader, CARD_TYPE_A, 1, total);
            else if ((result & 3) == 1) result |= reader_presence(&reader, total);
            else if ((result & 3) == 2) result |= reader_field_off(&reader, total);
            else result |= reader_exchange(&reader, reader.pn.frame + 11, 4, total);
        }
        if (reader.phase == READER_DONE) reader_release(&reader);
        if (reader.phase == READER_FAILED) reader_recover(&reader, total);
        result |= ccid_tx_push(&tx, scratch, written, usb_ep2 + 64);
        result |= ccid_tx_delivered(&tx, usb_ep2 + 64);
        if (usb_bulk_ready()) result |= usb_send_bulk(written);
        if (usb_out_pending) usb_release_out();
        if (usb_abort_pending) usb_abort_complete();
        usb_notify_slot(result & 1);
        result |= uart_receive(&byte);
        result |= uart_transmit(byte);
        if (uart_faulted()) { uart_stop(); uart_reset(); }
        if (result) { ccid_rx_stop(&rx); ccid_tx_stop(&tx, usb_ep2 + 64); }
    }
}
