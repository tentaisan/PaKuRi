/* SPDX-License-Identifier: AGPL-3.0-only */
/* Adapted from ManeKey ccid_stream.c and ctaphid_stream.c, 2026-10-25.
 * Standalone CCID framing, without HID/chunk/offload dependencies. */
#include "ccid_packet.h"

#ifndef MG_CCID_TX_ONLY
void ccid_rx_stop(CcidRx __xdata *s) MG_CALL {
    uint8_t i;
    for (i = 0; i < 10; ++i) s->header[i] = 0;
    s->used = 0; s->stopped = 1;
}
void ccid_rx_init(CcidRx __xdata *s, uint16_t maximum) MG_CALL {
    ccid_rx_stop(s);
    s->maximum = maximum; s->total = s->emitted = 0;
    s->stopped = maximum < 10;
}
uint8_t ccid_rx_push(CcidRx __xdata *s, const uint8_t __xdata *packet,
    uint8_t length, uint8_t __idata *consumed, uint8_t __xdata *output,
    uint8_t __idata *written) MG_CALL {
    uint8_t n;
    uint16_t body;
    *consumed = *written = 0;
    if (s->stopped || length > 64 || (s->total && s->emitted == s->total)) goto fail;
    while (s->used < 10 && *consumed < length)
        s->header[s->used++] = packet[(*consumed)++];
    if (s->used < 10) return 1;
    if (!s->total) {
        if (s->header[3] || s->header[4]) goto fail;
        body = (uint16_t)s->header[1] | ((uint16_t)s->header[2] << 8);
        if (body > s->maximum - 10) goto fail;
        s->total = body + 10;
    }
    body = s->emitted < 10 ? s->total - 10 : s->total - s->emitted;
    if (length - *consumed > body) goto fail;
    if (!s->emitted) {
        for (n = 0; n < 10; ++n) output[(*written)++] = s->header[n];
        s->emitted = 10;
    }
    while (*consumed < length && *written < 54) {
        output[(*written)++] = packet[(*consumed)++]; ++s->emitted;
    }
    return 1;
fail:
    ccid_rx_stop(s); return 0;
}
#endif
#if defined(MG_SINGLETON) && defined(MG_CCID_TX_ONLY)
#include "gate.h"
#define TX(s) (&gate_state.tx)
#ifdef MG_COMPACT_ABI
#define VALID_TX(s) 1
#else
#define VALID_TX(s) ((s) == &gate_state.tx)
#endif
#else
#define TX(s) (s)
#define VALID_TX(s) 1
#endif
void MG_ENTRY(ccid_tx_stop)(MG_SELF_PARAM(CcidTx, s) uint8_t __xdata *packet) MG_CALL {
    if (!VALID_TX(s)) return;
#ifdef MG_UID_PROFILE
    wipe_xdata(packet,64);
#else
    uint8_t i;
    for (i = 0; i < 64; ++i) packet[i] = 0;
#endif
    TX(s)->total = TX(s)->copied = 0;
    TX(s)->used = TX(s)->waiting = TX(s)->complete = 0; TX(s)->stopped = 1;
}
uint8_t MG_ENTRY(ccid_tx_init)(MG_SELF_PARAM(CcidTx, s) uint16_t total,
    uint8_t __xdata *packet) MG_CALL {
    if (!VALID_TX(s)) return 0;
    ccid_tx_stop(MG_OWNER(s, TX(s)), packet); TX(s)->total = total;
    if (total < 10) return 0;
    TX(s)->stopped = 0; return 1;
}
uint8_t MG_ENTRY(ccid_tx_push)(MG_SELF_PARAM(CcidTx, s) const uint8_t __xdata *data,
    uint8_t length, uint8_t __xdata *packet) MG_CALL {
    if (!VALID_TX(s)) return 0;
#ifdef MG_UID_PROFILE
    uint8_t count;
#else
    uint8_t count, i;
#endif
    if (TX(s)->stopped || TX(s)->complete || TX(s)->waiting) return 0;
    if (length > TX(s)->total - TX(s)->copied) { ccid_tx_stop(MG_OWNER(s, TX(s)), packet); return 0; }
    count = 64 - TX(s)->used;
    if (length < count) count = length;
#ifdef MG_UID_PROFILE
    copy_xdata(packet+TX(s)->used,data,count);
#else
    for (i = 0; i < count; ++i) packet[TX(s)->used + i] = data[i];
#endif
    TX(s)->used += count; TX(s)->copied += count;
    if (TX(s)->used == 64 || TX(s)->copied == TX(s)->total) TX(s)->waiting = 1;
    return count;
}
uint8_t MG_ENTRY(ccid_tx_delivered)(MG_SELF_PARAM(CcidTx, s) uint8_t __xdata *packet) MG_CALL {
    if (!VALID_TX(s)) return 0;
#ifdef MG_UID_PROFILE
    uint8_t length;
#else
    uint8_t length, i;
#endif
    if (TX(s)->stopped || !TX(s)->waiting) return 0;
    length = TX(s)->used;
#ifdef MG_UID_PROFILE
    wipe_xdata(packet,64);
#else
    for (i = 0; i < 64; ++i) packet[i] = 0;
#endif
    TX(s)->used = 0;
    if (length == 64 && TX(s)->copied == TX(s)->total) return 1;
    TX(s)->waiting = 0;
    TX(s)->complete = TX(s)->copied == TX(s)->total;
    return 1;
}
