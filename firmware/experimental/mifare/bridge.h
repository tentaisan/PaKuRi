/* SPDX-License-Identifier: AGPL-3.0-only */
#ifndef MG_CLASSIC_BRIDGE_H
#define MG_CLASSIC_BRIDGE_H
#ifdef __SDCC
#error Experimental bridge is host-only until CH559 memory and ABI are designed
#endif
#include "classic.h"
#include "../../src/pn532_transport.h"

enum { MB_IDLE, MB_PENDING, MB_REPLY, MB_INVALID };
typedef struct {
    McSession card;
    PnTransport *pn;
    uint8_t response[18];
    size_t response_len;
    uint8_t state;
} MfBridge;

void mb_init(MfBridge *b, PnTransport *pn);
int mb_attach(MfBridge *b, const uint8_t *uid, size_t n);
int mb_submit(MfBridge *b, const uint8_t *apdu, size_t n, uint16_t now);
void mb_poll(MfBridge *b, uint16_t now);
int mb_take(MfBridge *b, uint8_t *out, size_t cap, size_t *n);



void mb_invalidate(MfBridge *b, uint16_t now);
#endif
