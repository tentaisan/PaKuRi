/* SPDX-License-Identifier: Apache-2.0 */
#include "../experimental/standalone/dispatch.h"
#include "../src/events.h"
#include <assert.h>

uint8_t mg_standalone_reader(void) { return 0; }
uint8_t mg_standalone_card(void) { return 0; }
uint8_t mg_standalone_host(void) { return 0; }

int main(void) {
    mg_events_clear();
    mg_events_publish(MG_EVENT_READER_READY | MG_EVENT_CARD_PRESENT);
    mg_dispatch_poll();
    assert(mg_events_take() == (MG_EVENT_READER_READY | MG_EVENT_CARD_PRESENT));
    return 0;
}
