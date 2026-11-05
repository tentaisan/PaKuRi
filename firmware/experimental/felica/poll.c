/* SPDX-License-Identifier: AGPL-3.0-only */
#include "poll.h"

int fp_poll_request(uint8_t *out, size_t cap) {

    static const uint8_t request[] = {1, 1, 0, 0xff, 0xff, 0, 0};
    size_t i;
    if (!out || cap < sizeof request) return FP_INVALID;
    for (i = 0; i < sizeof request; ++i) out[i] = request[i];
    return (int)sizeof request;
}

void fp_clear(FPoll *s) {
    size_t i;
    if (!s) return;
    for (i = 0; i < sizeof s->idm; ++i) s->idm[i] = 0;
    s->present = 0;
}

int fp_parse(FPoll *s, const uint8_t *reply, size_t n) {
    size_t i;
    if (!s) return FP_INVALID;
    fp_clear(s);
    if (!reply) return FP_INVALID;
    if (n == 1 && reply[0] == 0) return FP_NONE;

    if ((n != 20 && n != 22) || reply[0] != 1 || reply[1] != 1 ||
        reply[2] != n - 2 || reply[3] != 1) return FP_INVALID;
    for (i = 0; i < 8; ++i) s->idm[i] = reply[4 + i];
    s->present = 1;
    return FP_FOUND;
}

int fp_get_data(const FPoll *s, const uint8_t *apdu, size_t n,
                uint8_t *out, size_t cap, size_t *out_n) {
    size_t i;
    if (!out_n) return FP_INVALID;
    *out_n = 0;
    if (!s || !s->present || !apdu || n != 5 || !out || cap < 10 ||
        apdu[0] != 0xff || apdu[1] != 0xca || apdu[2] || apdu[3] || apdu[4])
        return FP_INVALID;
    for (i = 0; i < 8; ++i) out[i] = s->idm[i];
    out[8] = 0x90; out[9] = 0;
    *out_n = 10;
    return FP_FOUND;
}
