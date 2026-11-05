/* SPDX-License-Identifier: Apache-2.0 */
#include "../experimental/standalone/dispatch.h"
#include "../src/events.h"
#include <assert.h>

static uint8_t changes, reader, card, host, calls[2];
static MgDispatchSnapshot seen[2];
uint8_t mg_standalone_reader(void) { return reader; }
uint8_t mg_standalone_card(void) { return card; }
uint8_t mg_standalone_host(void) { return host; }
uint8_t mg_standalone_take(void) { uint8_t v=changes; changes=0; return v; }
void second(const MgDispatchSnapshot *s) { seen[1]=*s; ++calls[1]; }
void first(const MgDispatchSnapshot *s) {
    seen[0]=*s; ++calls[0];
    if (calls[0] == 1) {

        mg_events_publish(MG_EVENT_USB_RESET);
        mg_dispatch_poll();
    }
}
int main(void) {
    MgStandaloneState current;
    mg_events_clear();
    reader=MG_S_READER_READY; card=1; host=1;
    changes=MG_S_EVENT_CARD; mg_events_publish(MG_EVENT_CARD_PRESENT);
    mg_dispatch_current(0); mg_dispatch_current(&current);
    assert(current.reader==reader && current.card_present==card && current.host_connected==host);
    mg_dispatch_poll();
    assert(calls[0]==1 && calls[1]==1);
    assert(seen[0].state.reader==reader && seen[0].state.card_present==card && seen[0].state.host_connected==host);
    assert(seen[0].changes==MG_S_EVENT_CARD && seen[0].events==MG_EVENT_CARD_PRESENT);
    assert(seen[1].state.reader==reader && seen[1].state.card_present==card && seen[1].state.host_connected==host);
    assert(seen[1].changes==seen[0].changes && seen[1].events==seen[0].events);
    mg_dispatch_poll();
    assert(calls[0]==2 && calls[1]==2);
    assert(seen[0].changes==0 && seen[0].events==MG_EVENT_USB_RESET && seen[1].events==seen[0].events);
    mg_dispatch_poll(); assert(calls[0]==2 && calls[1]==2);
    return 0;
}
