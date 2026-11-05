/* SPDX-License-Identifier: AGPL-3.0-only */
#ifndef PAKURI_STANDALONE_STATE_H
#define PAKURI_STANDALONE_STATE_H
#include <stdint.h>
#ifdef __SDCC
#define MG_STANDALONE_CALL __reentrant
#define MG_STATE_XDATA __xdata
#else
#define MG_STANDALONE_CALL
#define MG_STATE_XDATA
#endif


enum { MG_S_READER_STARTING, MG_S_READER_READY, MG_S_READER_FAILED };
enum { MG_S_EVENT_READER = 1, MG_S_EVENT_CARD = 2, MG_S_EVENT_HOST = 4 };
typedef struct { uint8_t reader, card_present, host_connected; } MgStandaloneState;

uint8_t mg_standalone_update(MgStandaloneState MG_STATE_XDATA *state, const MgStandaloneState MG_STATE_XDATA *observed) MG_STANDALONE_CALL;

uint8_t mg_standalone_observe(MgStandaloneState MG_STATE_XDATA *state) MG_STANDALONE_CALL;

void mg_standalone_init(void);
void mg_standalone_poll(void);
uint8_t mg_standalone_take(void);
uint8_t mg_standalone_reader(void);
uint8_t mg_standalone_card(void);
uint8_t mg_standalone_host(void);
#endif
