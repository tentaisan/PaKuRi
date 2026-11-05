/* SPDX-License-Identifier: AGPL-3.0-only */
#ifndef PAKURI_STANDALONE_DISPATCH_H
#define PAKURI_STANDALONE_DISPATCH_H
#include "state.h"


typedef struct {
    MgStandaloneState state;
    uint8_t changes;
    uint16_t events;
} MgDispatchSnapshot;

#ifdef MG_DISPATCH_CONSUMER_1
void MG_DISPATCH_CONSUMER_1(const MgDispatchSnapshot MG_STATE_XDATA *snapshot);
#endif
#ifdef MG_DISPATCH_CONSUMER_2
void MG_DISPATCH_CONSUMER_2(const MgDispatchSnapshot MG_STATE_XDATA *snapshot);
#endif

void mg_dispatch_current(MgStandaloneState MG_STATE_XDATA *state) MG_STANDALONE_CALL;
void mg_dispatch_poll(void);
#endif
