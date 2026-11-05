/* SPDX-License-Identifier: AGPL-3.0-only */
#ifndef MG_EXPERIMENTAL_CCID_BRIDGE_H
#define MG_EXPERIMENTAL_CCID_BRIDGE_H
#include "bridge.h"


typedef struct { MfBridge *bridge; uint8_t active, sequence; } MfCcid;
void mfc_init(MfCcid *c, MfBridge *b);
int mfc_submit(MfCcid *c, const uint8_t *message, size_t n, uint16_t now);
void mfc_poll(MfCcid *c, uint16_t now);
int mfc_take(MfCcid *c, uint8_t *message, size_t capacity, size_t *n);
void mfc_invalidate(MfCcid *c, uint16_t now);
#endif
