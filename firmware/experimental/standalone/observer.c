/* SPDX-License-Identifier: AGPL-3.0-only */
#include "state.h"
#include "../../src/reader.h"
#include "../../src/usb_device.h"
#ifdef __SDCC
#define MG_STANDALONE_XDATA __xdata
#else
#define MG_STANDALONE_XDATA
#endif
static MG_STANDALONE_XDATA MgStandaloneState current;
static MG_STANDALONE_XDATA MgStandaloneState sample;
static MG_STANDALONE_XDATA uint8_t pending;

uint8_t mg_standalone_observe(MgStandaloneState MG_STATE_XDATA *state) MG_STANDALONE_CALL {
    sample.reader = reader_state.phase == READER_FAILED ? MG_S_READER_FAILED :
                    reader_state.initialized ? MG_S_READER_READY : MG_S_READER_STARTING;
    sample.card_present = reader_state.present != 0;
    sample.host_connected = usb_configured != 0;
    return mg_standalone_update(state, &sample);
}
void mg_standalone_init(void) {
    current.reader=MG_S_READER_STARTING; current.card_present=0; current.host_connected=0; pending=0;
}
void mg_standalone_poll(void) { pending |= mg_standalone_observe(&current); }
uint8_t mg_standalone_take(void) { uint8_t result=pending; pending=0; return result; }
uint8_t mg_standalone_reader(void) { return current.reader; }
uint8_t mg_standalone_card(void) { return current.card_present; }
uint8_t mg_standalone_host(void) { return current.host_connected; }
