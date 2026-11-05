/* SPDX-License-Identifier: AGPL-3.0-only */
#include "events.h"
#ifdef MG_EVENTS

static uint16_t pending;
void mg_events_publish(uint16_t flags) { pending |= flags; }
uint16_t mg_events_take(void) { uint16_t result = pending; pending = 0; return result; }
void mg_events_clear(void) { pending = 0; }
#endif
