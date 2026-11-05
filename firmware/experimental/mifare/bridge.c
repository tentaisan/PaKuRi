/* SPDX-License-Identifier: AGPL-3.0-only */
#include "bridge.h"

static void wipe(void *data, size_t len) {
    volatile uint8_t *p = data;
    while (len--) *p++ = 0;
}
void mb_init(MfBridge *b, PnTransport *pn) {
    wipe(b, sizeof(*b)); b->pn = pn; b->state = MB_INVALID;
}
void mb_invalidate(MfBridge *b, uint16_t now) {
    if (!b || !b->pn) return;
    mc_clear(&b->card);
    wipe(b->response, sizeof(b->response)); b->response_len = 0;
    if (b->pn->phase == PN_DONE) pn_transport_release(b->pn);
    else if (b->pn->phase != PN_READY && b->pn->phase != PN_CLOSED)
        pn_transport_recover(b->pn, now);
    b->state = MB_INVALID;
}
int mb_attach(MfBridge *b, const uint8_t *uid, size_t n) {
    if (!b || !b->pn || b->pn->phase != PN_READY || b->state != MB_INVALID) return 0;
    if (!mc_attach(&b->card, uid, n)) return 0;
    b->state = MB_IDLE; return 1;
}
int mb_submit(MfBridge *b, const uint8_t *apdu, size_t n, uint16_t now) {
    uint8_t tmp[32], error; size_t count = 0; int result;
    if (!b || !b->pn || b->state != MB_IDLE || b->pn->phase != PN_READY) return 0;
    result = mc_command(&b->card, apdu, n, tmp, sizeof(tmp), &count);
    if (result == MC_RESPONSE) {
        if (count > sizeof(b->response)) { wipe(tmp, sizeof(tmp)); mb_invalidate(b, now); return 0; }
        for (size_t i = 0; i < count; ++i) b->response[i] = tmp[i];
        b->response_len = count; b->state = MB_REPLY;
        wipe(tmp, sizeof(tmp)); return 1;
    }
    if (result != MC_EXCHANGE) { wipe(tmp, sizeof(tmp)); return 0; }
    error = pn_transport_begin(b->pn, 0x40, tmp, (uint16_t)count, 17, now, 15000);
    wipe(tmp, sizeof(tmp));
    if (error) { mb_invalidate(b, now); return 0; }
    b->state = MB_PENDING; return 1;
}
void mb_poll(MfBridge *b, uint16_t now) {
    int result;
    if (!b || !b->pn || b->state != MB_PENDING) return;
    pn_transport_poll(b->pn, now);
    if (b->pn->phase == PN_FAILED) { mb_invalidate(b, now); return; }
    if (b->pn->phase != PN_DONE) return;
    result = mc_complete(&b->card, b->pn->frame + b->pn->offset,
                         b->pn->payload, b->response, sizeof(b->response), &b->response_len);
    pn_transport_release(b->pn);
    if (result != MC_RESPONSE) { mb_invalidate(b, now); return; }
    b->state = MB_REPLY;
}
int mb_take(MfBridge *b, uint8_t *out, size_t cap, size_t *n) {
    size_t i;
    if (!b || !out || !n || b->state != MB_REPLY || cap < b->response_len) return 0;
    for (i = 0; i < b->response_len; ++i) out[i] = b->response[i];
    *n = b->response_len;
    wipe(b->response, sizeof(b->response)); b->response_len = 0; b->state = MB_IDLE;
    return 1;
}
