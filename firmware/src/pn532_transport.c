/* SPDX-License-Identifier: Apache-2.0 */
/* ManeKey driver.rs synchronization semantics adapted to polled UART, 2026-10-25.
 * UART abort/drain state machine is new. No application command is retried. */
#include "pn532_transport.h"
#include "uart.h"
#ifdef MG_SINGLETON

#include "reader.h"
#define T(s) (&reader_state.pn)
#ifdef MG_COMPACT_ABI
#define VALID_TRANSPORT(s) 1
#else
#define VALID_TRANSPORT(s) ((s) == &reader_state.pn)
#endif
#define PRIVATE_TRANSPORT_PARAM
#define PRIVATE_TRANSPORT_ONLY_PARAM void
#define PRIVATE_TRANSPORT_ARG
#define PRIVATE_TRANSPORT_ONLY_ARG
#else
#define T(s) (s)
#define VALID_TRANSPORT(s) 1
#define PRIVATE_TRANSPORT_PARAM PnTransport __xdata *s,
#define PRIVATE_TRANSPORT_ONLY_PARAM PnTransport __xdata *s
#define PRIVATE_TRANSPORT_ARG s,
#define PRIVATE_TRANSPORT_ONLY_ARG s
#endif

static __data uint8_t io_byte;
#ifdef MG_UART_DIAGNOSTIC
volatile __data uint8_t pn_uart_diagnostic;
enum {
    PN_DIAG_RX_FAULT = 0x10,
    PN_DIAG_TX_BUSY = 0x20,
    PN_DIAG_UNEXPECTED_RX = 0x30,
    PN_DIAG_TIMEOUT = 0x40
};
#define UART_FAIL(reason) do { \
    pn_uart_diagnostic = (reason) | T(s)->phase; \
    fail(PRIVATE_TRANSPORT_ARG PN_ERR_UART); \
} while (0)
#else
#define UART_FAIL(reason) fail(PRIVATE_TRANSPORT_ARG PN_ERR_UART)
#endif

static uint8_t ack_byte(uint8_t at) {
    return at == 2 || at == 4 ? 0xff : 0;
}
#ifdef MG_UID_PROFILE
static uint8_t drain_uart(void) MG_CALL {
    uint8_t i;
    for (i=0;i<64 && uart_receive(&io_byte);++i) { }
    return i;
}
#endif
static void wipe(PRIVATE_TRANSPORT_ONLY_PARAM) MG_CALL {
#ifdef MG_UID_PROFILE
    wipe_xdata(T(s)->frame,PN532_FRAME_MAX);
#else
    uint16_t i;
    for (i = 0; i < PN532_FRAME_MAX; ++i) T(s)->frame[i] = 0;
#endif
    T(s)->total = T(s)->cursor = T(s)->expected = T(s)->offset = T(s)->payload = 0;
}
static void fail(PRIVATE_TRANSPORT_PARAM uint8_t MG_LOCAL error) MG_CALL {
    T(s)->error = error; T(s)->phase = PN_FAILED; T(s)->verifying = 0;

}
void MG_ENTRY(pn_transport_init)(MG_SELF_ONLY(PnTransport, s)) MG_CALL {
    if (!VALID_TRANSPORT(s)) return;
#ifdef MG_UART_DIAGNOSTIC
    pn_uart_diagnostic = 0;
#endif
    wipe(PRIVATE_TRANSPORT_ONLY_ARG); T(s)->phase = PN_CLOSED; T(s)->error = T(s)->verifying = 0;
    T(s)->command = 0; T(s)->bound = T(s)->deadline = T(s)->quiet_since = 0;
    T(s)->support = 0;
}
uint8_t MG_ENTRY(pn_transport_begin)(MG_SELF_PARAM(PnTransport, s) uint8_t MG_LOCAL command,
    const uint8_t __xdata *MG_LOCAL data, uint16_t MG_LOCAL length, uint16_t MG_LOCAL response_bound,
    uint16_t MG_LOCAL now, uint16_t MG_LOCAL timeout) MG_CALL {
    if (!VALID_TRANSPORT(s)) return PN_ERR_ARGUMENT;
    uint8_t error;
    if (T(s)->phase != PN_READY) return PN_ERR_BUSY;
    if (!timeout || timeout > 30000 || response_bound > PN532_PACKET_MAX - 2)
        return PN_ERR_ARGUMENT;
#ifdef MG_UART_DIAGNOSTIC
    if (uart_faulted()) { UART_FAIL(PN_DIAG_RX_FAULT); return T(s)->error; }
    if (!uart_tx_idle()) { UART_FAIL(PN_DIAG_TX_BUSY); return T(s)->error; }
#else
    if (uart_faulted() || !uart_tx_idle()) { fail(PRIVATE_TRANSPORT_ARG PN_ERR_UART); return T(s)->error; }
#endif
    if (uart_receive(&io_byte)) { UART_FAIL(PN_DIAG_UNEXPECTED_RX); return T(s)->error; }
    error = pn532_encode(command, data, length, T(s)->frame, PN532_FRAME_MAX, &T(s)->total);
    if (error) return error;
    T(s)->command = command; T(s)->bound = response_bound;
    T(s)->deadline = now + timeout; T(s)->cursor = T(s)->expected = T(s)->offset = T(s)->payload = 0;
    T(s)->error = 0; T(s)->phase = PN_SEND;
    return PN_OK;
}
void MG_ENTRY(pn_transport_release)(MG_SELF_ONLY(PnTransport, s)) MG_CALL {
    if (!VALID_TRANSPORT(s)) return;
    if (T(s)->phase != PN_DONE) return;
    wipe(PRIVATE_TRANSPORT_ONLY_ARG); T(s)->phase = PN_READY;
}
void MG_ENTRY(pn_transport_recover)(MG_SELF_PARAM(PnTransport, s) uint16_t MG_LOCAL now) MG_CALL {
    if (!VALID_TRANSPORT(s)) return;
    uint16_t i;
    uint8_t sum = 0;

    if (T(s)->phase >= PN_REC_FINISH || T(s)->verifying) return;


    if (T(s)->phase != PN_SEND && T(s)->phase != PN_TX_FINISH &&
        !(T(s)->phase == PN_FAILED && T(s)->expected == 0 && T(s)->cursor < T(s)->total)) {
        T(s)->cursor = T(s)->total = 0;
    }
    if (T(s)->total >= 2 && T(s)->cursor <= T(s)->total - 2) {

        i = T(s)->frame[3] == 0xff && T(s)->frame[4] == 0xff ? 8 : 5;
        for (; i < T(s)->total - 2; ++i) sum += T(s)->frame[i];
        T(s)->frame[T(s)->total - 2] = (uint8_t)(1 - sum);
    }
    T(s)->error = PN_ERR_CANCELLED; T(s)->verifying = T(s)->support = 0;
    T(s)->phase = PN_REC_FINISH; T(s)->deadline = now + 1000;
    uart_reset();
}

void MG_ENTRY(pn_transport_poll)(MG_SELF_PARAM(PnTransport, s) uint16_t MG_LOCAL now) MG_CALL {
    if (!VALID_TRANSPORT(s)) return;
    uint8_t n, error;
    if (T(s)->phase == PN_CLOSED || T(s)->phase == PN_FAILED) return;
    if (T(s)->phase == PN_READY || T(s)->phase == PN_DONE) {
#ifdef MG_UART_DIAGNOSTIC
        if (uart_faulted()) UART_FAIL(PN_DIAG_RX_FAULT);
        else if (uart_receive(&io_byte)) UART_FAIL(PN_DIAG_UNEXPECTED_RX);
#else
        if (uart_faulted() || uart_receive(&io_byte)) fail(PRIVATE_TRANSPORT_ARG PN_ERR_UART);
#endif
        return;
    }
    if ((int16_t)(now - T(s)->deadline) >= 0) {
#ifdef MG_UART_DIAGNOSTIC
        pn_uart_diagnostic = PN_DIAG_TIMEOUT | T(s)->phase;
#endif
        fail(PRIVATE_TRANSPORT_ARG  PN_ERR_TIMEOUT); return;
    }
    if (uart_faulted()) { UART_FAIL(PN_DIAG_RX_FAULT); return; }

    if (T(s)->phase == PN_REC_FINISH) {


#ifdef MG_UID_PROFILE
        drain_uart();
#else
        for (n = 0; n < 64 && uart_receive(&io_byte); ++n) { }
#endif
        if (T(s)->cursor < T(s)->total) {
            if (uart_transmit(T(s)->frame[T(s)->cursor])) ++T(s)->cursor;
        } else if (uart_tx_idle()) { wipe(PRIVATE_TRANSPORT_ONLY_ARG); T(s)->phase = PN_REC_WAKE; }
        return;
    }
    if (T(s)->phase == PN_REC_WAKE) {
        if (uart_transmit(0x55)) { T(s)->quiet_since = now; T(s)->phase = PN_REC_WAKE_WAIT; }
        return;
    }
    if (T(s)->phase == PN_REC_WAKE_WAIT) {
#ifdef MG_UID_PROFILE
        drain_uart();
#else
        for (n = 0; n < 64 && uart_receive(&io_byte); ++n) { }
#endif
        if (uart_tx_idle() && (uint16_t)(now - T(s)->quiet_since) >= 5) {
            T(s)->cursor = 0; T(s)->phase = PN_REC_ABORT;
        }
        return;
    }
    if (T(s)->phase == PN_REC_ABORT) {
#ifdef MG_UID_PROFILE
        drain_uart();
#else
        for (n = 0; n < 64 && uart_receive(&io_byte); ++n) { }
#endif
        if (uart_transmit(ack_byte(T(s)->cursor)) && ++T(s)->cursor == 6)
            T(s)->phase = PN_REC_ABORT_WAIT;
        return;
    }
    if (T(s)->phase == PN_REC_ABORT_WAIT) {
#ifdef MG_UID_PROFILE
        drain_uart();
#else
        for (n = 0; n < 64 && uart_receive(&io_byte); ++n) { }
#endif
        if (uart_tx_idle()) { T(s)->quiet_since = now; T(s)->phase = PN_REC_DRAIN; }
        return;
    }
    if (T(s)->phase == PN_REC_DRAIN) {
#ifdef MG_UID_PROFILE
        if (drain_uart()) T(s)->quiet_since = now;
#else
        for (n = 0; n < 64 && uart_receive(&io_byte); ++n) T(s)->quiet_since = now;
#endif
        if ((uint16_t)(now - T(s)->quiet_since) >= 20) {
            wipe(PRIVATE_TRANSPORT_ONLY_ARG);
            T(s)->phase = PN_READY;
            error = pn_transport_begin(MG_OWNER(s, T(s)), 2, T(s)->frame, 0, 4, now, 500);
            if (error) { fail(PRIVATE_TRANSPORT_ARG  error); return; }
            T(s)->verifying = 1;
        }
        return;
    }
    if (T(s)->phase == PN_SEND) {
        if (uart_receive(&io_byte)) { UART_FAIL(PN_DIAG_UNEXPECTED_RX); return; }
        if (uart_transmit(T(s)->frame[T(s)->cursor]) && ++T(s)->cursor == T(s)->total)
            T(s)->phase = PN_TX_FINISH;
        return;
    }
    if (T(s)->phase == PN_TX_FINISH) {
        if (!uart_tx_idle()) return;
        T(s)->cursor = 0; T(s)->total = 0; T(s)->expected = 6; T(s)->phase = PN_ACK;
    }
    for (n = 0; n < 64 && uart_receive(&io_byte); ++n) {
        if (T(s)->cursor >= PN532_FRAME_MAX) { fail(PRIVATE_TRANSPORT_ARG  PN_TOO_LONG); return; }
        T(s)->frame[T(s)->cursor++] = io_byte;
        if (T(s)->phase == PN_ACK) {
            if (io_byte != ack_byte((uint8_t)(T(s)->cursor - 1))) {
                fail(PRIVATE_TRANSPORT_ARG  PN_ERR_ACK); return;
            }
            if (T(s)->cursor == 6) { T(s)->cursor = T(s)->expected = 0; T(s)->phase = PN_RESPONSE; }
            continue;
        }
        if (!T(s)->expected && (T(s)->cursor == 5 || T(s)->cursor == 8)) {
            error = pn532_frame_length(T(s)->frame, T(s)->cursor, &T(s)->expected);
            if (error && error != PN_TRUNCATED) { fail(PRIVATE_TRANSPORT_ARG  error); return; }
        }
        if (T(s)->expected && T(s)->cursor == T(s)->expected) {
            error = pn532_decode(T(s)->command, T(s)->frame, T(s)->cursor, &T(s)->offset, &T(s)->payload);
            if (error) { fail(PRIVATE_TRANSPORT_ARG  error); return; }
            if (T(s)->payload > T(s)->bound) { fail(PRIVATE_TRANSPORT_ARG  PN_ERR_RESPONSE_BOUND); return; }
            if (uart_receive(&io_byte)) { fail(PRIVATE_TRANSPORT_ARG  PN_TRAILING); return; }
            if (T(s)->verifying) {
                if (T(s)->payload != 4 || T(s)->frame[T(s)->offset] != 0x32) {
                    fail(PRIVATE_TRANSPORT_ARG  PN_ERR_FIRMWARE); return;
                }
                T(s)->support = T(s)->frame[T(s)->offset + 3];
                T(s)->verifying = 0; wipe(PRIVATE_TRANSPORT_ONLY_ARG); T(s)->error = 0; T(s)->phase = PN_READY;
            } else T(s)->phase = PN_DONE;
            return;
        }
    }
}
