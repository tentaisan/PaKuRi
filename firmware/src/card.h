/* SPDX-License-Identifier: Apache-2.0 */
/* Type Bの境界検査はManeKey reader.rsから2026-10-25改変。 */
#ifndef PAKURI_CARD_H
#define PAKURI_CARD_H
#include "memory.h"
#if defined(MG_CH559_CLASSIC) && (!defined(MG_CH559) || !defined(MG_UID_PROFILE) || !defined(MG_SINGLETON) || !defined(MG_COMPACT_ABI))
#error CH559 Classic experiment requires the single-owner CH559 compact UID profile
#endif
#if defined(MG_CH559_FELICA) && !defined(MG_CH559_CLASSIC)
#error CH559 FeliCa experiment requires the CH559 Classic experimental profile
#endif
#define CARD_TYPE_A 0
#define CARD_TYPE_B 3
#ifdef MG_UID_PROFILE
#define CARD_TYPE_STORAGE_A 1
#endif
#ifdef MG_CH559_FELICA
#define CARD_SCAN_F 1
#define CARD_TYPE_STORAGE_F 2
#endif
#define CARD_ATR_MAX 20
enum { CARD_FOUND, CARD_NONE, CARD_UNSUPPORTED, CARD_INVALID };
typedef struct {
    uint8_t atr[CARD_ATR_MAX], atr_length, type, cid;
#ifdef MG_UID_PROFILE
    uint8_t uid[10];
#endif
#ifdef MG_CH559_CLASSIC

    uint8_t classic_candidate;
#endif
} CardInfo;


uint8_t card_parse(CardInfo __xdata *MG_LOCAL card, uint8_t MG_LOCAL type,
    const uint8_t __xdata *MG_LOCAL reply, uint16_t MG_LOCAL length) MG_CALL;
void card_clear(CardInfo __xdata *MG_LOCAL card) MG_CALL;
uint8_t card_short_apdu(const uint8_t __xdata *MG_LOCAL data, uint16_t MG_LOCAL length) MG_CALL;
#endif
