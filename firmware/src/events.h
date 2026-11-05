/* SPDX-License-Identifier: AGPL-3.0-only */
#ifndef PAKURI_EVENTS_H
#define PAKURI_EVENTS_H
#include <stdint.h>


enum {
    MG_EVENT_READER_READY = 0x0001,
    MG_EVENT_CARD_PRESENT = 0x0002,
    MG_EVENT_CARD_ABSENT = 0x0004,
    MG_EVENT_EXCHANGE_START = 0x0008,
    MG_EVENT_EXCHANGE_DONE = 0x0010,
    MG_EVENT_EXCHANGE_FAILED = 0x0020,
    MG_EVENT_READER_FAILED = 0x0040,
    MG_EVENT_USB_RESET = 0x0080,
    MG_EVENT_EXCHANGE_CANCELLED = 0x0100,
    MG_EVENT_USB_FAULT = 0x0200
};
#ifdef MG_EVENTS
void mg_events_publish(uint16_t flags);
uint16_t mg_events_take(void);
void mg_events_clear(void);
#else

#define mg_events_publish(flags) ((void)0)
#define mg_events_clear() ((void)0)
#endif
#endif
