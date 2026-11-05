/* SPDX-License-Identifier: AGPL-3.0-only */
#ifndef PAKURI_GATE_H
#define PAKURI_GATE_H
#include "reader.h"
#include "ccid_packet.h"
#include "usb_device.h"
enum {
    GATE_IDLE, GATE_RECEIVE, GATE_POWER_CLEAN, GATE_POWER_OFF, GATE_POWER_DELAY,
    GATE_POWER_A, GATE_POWER_B, GATE_EXCHANGE, GATE_OFF_START, GATE_OFF, GATE_ABORT, GATE_REPLY
#ifdef MG_CH559_FELICA
    , GATE_POWER_F
#endif
};
typedef struct {
    CcidTx tx;
    uint8_t header[10], parameters[8];
    uint16_t body_length, body_received, deadline, next_poll, next_extension, abort_deadline;
    uint16_t now;
    uint8_t job, header_used, out_at, command, sequence, slot, active, powered;
    uint8_t response, source, interim, background, bg_type, bg_tries;
    uint8_t reported, aborting, abort_matched, abort_failed, rx_closed, bulk_first;
    uint8_t startup_retry;
} Gate;
extern __xdata Gate gate_state;
void gate_init(uint16_t now);

void gate_poll(uint16_t now);
#endif
