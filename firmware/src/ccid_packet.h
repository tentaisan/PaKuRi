/* SPDX-License-Identifier: AGPL-3.0-only */
/* Adapted from ManeKey ccid_stream and ctaphid_stream, 2026-10-25.
 * HID/chunk/Main removed. Slot/command/abort/deadlines belong to the runtime. */
#ifndef PAKURI_CCID_PACKET_H
#define PAKURI_CCID_PACKET_H
#include "memory.h"
typedef struct {
    uint16_t maximum, total, emitted;
    uint8_t header[10], used, stopped;
} CcidRx;
typedef struct {
    uint16_t total, copied;
    uint8_t used, waiting, complete, stopped;
} CcidTx;
void ccid_rx_init(CcidRx __xdata *s, uint16_t maximum) MG_CALL;
void ccid_rx_stop(CcidRx __xdata *s) MG_CALL;


uint8_t ccid_rx_push(CcidRx __xdata *s, const uint8_t __xdata *packet,
    uint8_t length, uint8_t __idata *consumed, uint8_t __xdata *output,
    uint8_t __idata *written) MG_CALL;
uint8_t MG_ENTRY(ccid_tx_init)(MG_SELF_PARAM(CcidTx, s) uint16_t total,
    uint8_t __xdata *packet) MG_CALL;
uint8_t MG_ENTRY(ccid_tx_push)(MG_SELF_PARAM(CcidTx, s) const uint8_t __xdata *data,
    uint8_t length, uint8_t __xdata *packet) MG_CALL;


uint8_t MG_ENTRY(ccid_tx_delivered)(MG_SELF_PARAM(CcidTx, s) uint8_t __xdata *packet) MG_CALL;
void MG_ENTRY(ccid_tx_stop)(MG_SELF_PARAM(CcidTx, s) uint8_t __xdata *packet) MG_CALL;
#ifdef MG_COMPACT_ABI
#include "gate.h"
#define ccid_tx_init(s,total,packet) \
    ((s)==(&gate_state.tx) ? MG_ENTRY(ccid_tx_init)((total),(packet)) : 0)
#define ccid_tx_push(s,data,length,packet) \
    ((s)==(&gate_state.tx) ? MG_ENTRY(ccid_tx_push)((data),(length),(packet)) : 0)
#define ccid_tx_delivered(s,packet) \
    ((s)==(&gate_state.tx) ? MG_ENTRY(ccid_tx_delivered)((packet)) : 0)
#define ccid_tx_stop(s,packet) \
    ((s)==(&gate_state.tx) ? MG_ENTRY(ccid_tx_stop)((packet)) : (void)0)
#endif
#endif
