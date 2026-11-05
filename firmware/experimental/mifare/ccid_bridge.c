/* SPDX-License-Identifier: AGPL-3.0-only */
#include "ccid_bridge.h"

void mfc_init(MfCcid *c, MfBridge *b) {
    c->bridge = b; c->active = 0; c->sequence = 0;
}
void mfc_invalidate(MfCcid *c, uint16_t now) {
    if (!c || !c->bridge) return;
    mb_invalidate(c->bridge, now); c->active = 0; c->sequence = 0;
}
int mfc_submit(MfCcid *c, const uint8_t *m, size_t n, uint16_t now) {
    size_t body;
    if (!c || !c->bridge || !m || c->active || n < 10) return 0;
    body = (size_t)m[1] | ((size_t)m[2] << 8);
    if (m[0] != 0x6f || m[3] || m[4] || m[5] || m[7] || m[8] || m[9] ||
        body != n - 10 || body > 261) return 0;
    if (!mb_submit(c->bridge, m + 10, body, now)) return 0;
    c->sequence = m[6]; c->active = 1; return 1;
}
void mfc_poll(MfCcid *c, uint16_t now) {
    if (!c || !c->active) return;
    mb_poll(c->bridge, now);
    if (c->bridge->state == MB_INVALID) c->active = 2;
}
int mfc_take(MfCcid *c, uint8_t *m, size_t cap, size_t *n) {
    size_t body = 0, i;
    if (!c || !c->bridge || !m || !n || !c->active || cap < 10) return 0;
    if (c->active != 2) {
        if (c->bridge->state != MB_REPLY || cap - 10 < c->bridge->response_len) return 0;
        if (!mb_take(c->bridge, m + 10, cap - 10, &body)) return 0;
    }
    for (i = 0; i < 10; ++i) m[i] = 0;
    m[0] = 0x80; m[1] = (uint8_t)body; m[2] = (uint8_t)(body >> 8); m[6] = c->sequence;
    if (c->active == 2) { m[7] = 0x42; m[8] = 0xfe; }
    *n = body + 10; c->active = 0; c->sequence = 0; return 1;
}
