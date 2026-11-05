/* SPDX-License-Identifier: Apache-2.0 */
/* C/UART adaptation of ManeKey pn532 Driver synchronization rules, 2026-10-25.
 * HSU recovery is new; see docs/pn532-transport.md and UM0701-02. */
#ifndef PAKURI_PN532_TRANSPORT_H
#define PAKURI_PN532_TRANSPORT_H
#include "pn532_frame.h"
enum {
    PN_CLOSED, PN_READY, PN_SEND, PN_TX_FINISH, PN_ACK, PN_RESPONSE, PN_DONE,
    PN_FAILED, PN_REC_FINISH, PN_REC_WAKE, PN_REC_WAKE_WAIT,
    PN_REC_ABORT, PN_REC_ABORT_WAIT, PN_REC_DRAIN
};
enum {
    PN_ERR_BUSY = 32, PN_ERR_TIMEOUT, PN_ERR_UART, PN_ERR_ACK,
    PN_ERR_CANCELLED, PN_ERR_RESPONSE_BOUND, PN_ERR_FIRMWARE, PN_ERR_ARGUMENT
};
#ifdef MG_UART_DIAGNOSTIC


extern volatile __data uint8_t pn_uart_diagnostic;
#endif
typedef struct {
    uint8_t frame[PN532_FRAME_MAX];
    uint16_t total, cursor, expected, offset, payload, bound, deadline, quiet_since;
    uint8_t phase, command, error, verifying, support;
} PnTransport;

void MG_ENTRY(pn_transport_init)(MG_SELF_ONLY(PnTransport, s)) MG_CALL;


uint8_t MG_ENTRY(pn_transport_begin)(MG_SELF_PARAM(PnTransport, s) uint8_t MG_LOCAL command,
    const uint8_t __xdata *MG_LOCAL data, uint16_t MG_LOCAL length, uint16_t MG_LOCAL response_bound,
    uint16_t MG_LOCAL now, uint16_t MG_LOCAL timeout) MG_CALL;
void MG_ENTRY(pn_transport_poll)(MG_SELF_PARAM(PnTransport, s) uint16_t MG_LOCAL now) MG_CALL;


void MG_ENTRY(pn_transport_recover)(MG_SELF_PARAM(PnTransport, s) uint16_t MG_LOCAL now) MG_CALL;

void MG_ENTRY(pn_transport_release)(MG_SELF_ONLY(PnTransport, s)) MG_CALL;
#ifdef MG_COMPACT_ABI

#include "reader.h"
#define pn_transport_init(s) \
    ((s)==(&reader_state.pn) ? MG_ENTRY(pn_transport_init)() : (void)0)
#define pn_transport_begin(s,command,data,length,response_bound,now,timeout) \
    ((s)==(&reader_state.pn) ? MG_ENTRY(pn_transport_begin)((command),(data),(length),(response_bound),(now),(timeout)) : PN_ERR_ARGUMENT)
#define pn_transport_poll(s,now) \
    ((s)==(&reader_state.pn) ? MG_ENTRY(pn_transport_poll)((now)) : (void)0)
#define pn_transport_recover(s,now) \
    ((s)==(&reader_state.pn) ? MG_ENTRY(pn_transport_recover)((now)) : (void)0)
#define pn_transport_release(s) \
    ((s)==(&reader_state.pn) ? MG_ENTRY(pn_transport_release)() : (void)0)
#endif
#endif
