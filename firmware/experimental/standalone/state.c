/* SPDX-License-Identifier: AGPL-3.0-only */
#include "state.h"
uint8_t mg_standalone_update(MgStandaloneState MG_STATE_XDATA *state, const MgStandaloneState MG_STATE_XDATA *observed) MG_STANDALONE_CALL {
    uint8_t flags = 0;
    if (!state || !observed || observed->reader > MG_S_READER_FAILED ||
        observed->card_present > 1 || observed->host_connected > 1) return 0;
    if (state->reader != observed->reader) flags |= MG_S_EVENT_READER;
    if (state->card_present != observed->card_present) flags |= MG_S_EVENT_CARD;
    if (state->host_connected != observed->host_connected) flags |= MG_S_EVENT_HOST;
    state->reader = observed->reader;
    state->card_present = observed->card_present;
    state->host_connected = observed->host_connected;
    return flags;
}
