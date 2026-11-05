/* SPDX-License-Identifier: AGPL-3.0-only */
#ifndef MG_FELICA_POLL_H
#define MG_FELICA_POLL_H
#include <stddef.h>
#include <stdint.h>


typedef struct { uint8_t idm[8]; uint8_t present; } FPoll;
enum { FP_INVALID = -1, FP_NONE = 0, FP_FOUND = 1 };
void fp_clear(FPoll *s);

int fp_poll_request(uint8_t *out, size_t cap);

int fp_parse(FPoll *s, const uint8_t *reply, size_t n);

int fp_get_data(const FPoll *s, const uint8_t *apdu, size_t n,
                uint8_t *out, size_t cap, size_t *out_n);
#endif
