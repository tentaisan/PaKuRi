/* SPDX-License-Identifier: Apache-2.0 */
/* ManeKey reader.rsをC/非同期pollへ2026-10-25翻案。A/在席確認は新規。 */
#ifndef PAKURI_READER_H
#define PAKURI_READER_H
#include "card.h"
#include "pn532_transport.h"
enum {
    READER_CLOSED, READER_RECOVER, READER_VERSION, READER_SAM, READER_PARAMETERS,
    READER_RETRIES, READER_IDLE, READER_SCAN, READER_PRESENCE,
    READER_APDU, READER_OFF, READER_DONE, READER_FAILED
#if defined(MG_RAW_B_TIMED) || defined(MG_RF_WAIT) || defined(MG_SOFT_B)
    , READER_RAW_TIMINGS
#endif
#ifdef MG_UID_PROFILE
    , READER_STORAGE_DESELECT
#endif
#ifdef MG_CH559_CLASSIC
    , READER_CLASSIC
#endif
#ifdef MG_CH559_FELICA
    , READER_FELICA, READER_FELICA_RELEASE, READER_FELICA_PRESENCE, READER_FELICA_DROP
#endif
};
enum { READER_OK, READER_ABSENT, READER_BAD_CARD, READER_BAD_APDU, READER_BUSY, READER_LINK };
typedef struct {
    PnTransport pn;
    CardInfo card;

    uint8_t phase, present, active, selected, initialized, error, scan_type, activate, rf_status;
} Reader;
#ifdef MG_SINGLETON

extern __xdata Reader reader_state;
#endif
#ifdef MG_SCAN_DIAGNOSTIC


extern volatile __xdata uint8_t reader_scan_diagnostic[7];
#endif
void MG_ENTRY(reader_init)(MG_SELF_PARAM(Reader, r) uint16_t now) MG_CALL;
void MG_ENTRY(reader_recover)(MG_SELF_PARAM(Reader, r) uint16_t now) MG_CALL;
void MG_ENTRY(reader_poll)(MG_SELF_PARAM(Reader, r) uint16_t now) MG_CALL;
void MG_ENTRY(reader_release)(MG_SELF_ONLY(Reader, r)) MG_CALL;

uint8_t MG_ENTRY(reader_scan)(MG_SELF_PARAM(Reader, r) uint8_t type, uint8_t activate, uint16_t now) MG_CALL;
uint8_t MG_ENTRY(reader_presence)(MG_SELF_PARAM(Reader, r) uint16_t now) MG_CALL;
uint8_t MG_ENTRY(reader_field_off)(MG_SELF_PARAM(Reader, r) uint16_t now) MG_CALL;

uint8_t MG_ENTRY(reader_exchange)(MG_SELF_PARAM(Reader, r) const uint8_t __xdata *data,
    uint16_t length, uint16_t now) MG_CALL;
#ifdef MG_CH559_CLASSIC

uint8_t reader_classic_exchange(const uint8_t __xdata *MG_LOCAL data, uint16_t MG_LOCAL length, uint16_t MG_LOCAL now);
uint8_t reader_classic_held(uint16_t MG_LOCAL now);
#endif
#ifdef MG_CH559_FELICA
uint8_t reader_felica_exchange(const uint8_t __xdata *MG_LOCAL data, uint16_t MG_LOCAL length, uint16_t MG_LOCAL now);
#endif
#ifdef MG_COMPACT_ABI
#define reader_init(r,now) \
    ((r)==(&reader_state) ? MG_ENTRY(reader_init)((now)) : (void)0)
#define reader_recover(r,now) \
    ((r)==(&reader_state) ? MG_ENTRY(reader_recover)((now)) : (void)0)
#define reader_poll(r,now) \
    ((r)==(&reader_state) ? MG_ENTRY(reader_poll)((now)) : (void)0)
#define reader_release(r) \
    ((r)==(&reader_state) ? MG_ENTRY(reader_release)() : (void)0)
#define reader_scan(r,type,activate,now) \
    ((r)==(&reader_state) ? MG_ENTRY(reader_scan)((type),(activate),(now)) : READER_BUSY)
#define reader_presence(r,now) \
    ((r)==(&reader_state) ? MG_ENTRY(reader_presence)((now)) : READER_BUSY)
#define reader_field_off(r,now) \
    ((r)==(&reader_state) ? MG_ENTRY(reader_field_off)((now)) : READER_BUSY)
#define reader_exchange(r,data,length,now) \
    ((r)==(&reader_state) ? MG_ENTRY(reader_exchange)((data),(length),(now)) : READER_BUSY)
#endif
#endif
