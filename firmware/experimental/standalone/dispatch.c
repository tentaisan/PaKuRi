/* SPDX-License-Identifier: AGPL-3.0-only */
#include "dispatch.h"
#include "../../src/events.h"

#if defined(MG_DISPATCH_CONSUMER_1) || defined(MG_DISPATCH_CONSUMER_2)
static uint8_t delivering;
static MgDispatchSnapshot MG_STATE_XDATA snapshot;
#endif

void mg_dispatch_current(MgStandaloneState MG_STATE_XDATA *state) MG_STANDALONE_CALL {
    if (!state) return;
    state->reader = mg_standalone_reader();
    state->card_present = mg_standalone_card();
    state->host_connected = mg_standalone_host();
}

void mg_dispatch_poll(void) {
#if defined(MG_DISPATCH_CONSUMER_1) || defined(MG_DISPATCH_CONSUMER_2)
    if (delivering) return;
    delivering = 1;
    mg_dispatch_current(&snapshot.state);
    snapshot.changes = mg_standalone_take();
    snapshot.events = mg_events_take();
    if (snapshot.changes || snapshot.events) {
#ifdef MG_DISPATCH_CONSUMER_1
        MG_DISPATCH_CONSUMER_1(&snapshot);
#endif
#ifdef MG_DISPATCH_CONSUMER_2
        MG_DISPATCH_CONSUMER_2(&snapshot);
#endif
    }
    delivering = 0;
#endif
}
