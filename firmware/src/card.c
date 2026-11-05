/* SPDX-License-Identifier: Apache-2.0 */
/* ManeKey reader.rsのType B検査を改変。Type A/PCSC ATR生成は新規。
 * 根拠: UM0701-02 7.3.5、PC/SC Part3 Table3-5。 */
#include "card.h"

#ifdef MG_UID_PROFILE
void copy_xdata(uint8_t __xdata *dest, const uint8_t __xdata *src, uint16_t n) MG_CALL {
    while (n--) *dest++ = *src++;
}
void wipe_xdata(uint8_t __xdata *dest, uint16_t n) MG_CALL {
    while (n--) *dest++ = 0;
}
#endif
void card_clear(CardInfo __xdata *MG_LOCAL card) MG_CALL {
#ifdef MG_UID_PROFILE
    wipe_xdata((uint8_t __xdata *)card, sizeof(*card));
#else
    uint8_t MG_LOCAL i;
    for (i = 0; i < sizeof(*card); ++i) ((uint8_t __xdata *)card)[i] = 0;
#endif
}
uint8_t card_parse(CardInfo __xdata *MG_LOCAL card, uint8_t MG_LOCAL type,
    const uint8_t __xdata *MG_LOCAL reply, uint16_t MG_LOCAL length) MG_CALL {
#ifndef MG_RAW_B_TIMED
#ifdef MG_COMPACT_ABI
    uint8_t MG_LOCAL at, end;
#else
    uint16_t at, end;
#endif
    uint8_t MG_LOCAL historical, t0, i, sum;
#else
    uint8_t MG_LOCAL historical, i, sum;
#endif
    card_clear(card);
    if (length == 1 && !reply[0]) return CARD_NONE;
    if (length < 2 || length > 263 || reply[0] != 1 || reply[1] != 1) return CARD_INVALID;
    if (type == CARD_TYPE_A) {
#ifdef MG_RAW_B_TIMED


        return CARD_UNSUPPORTED;
#else
#ifdef MG_COMPACT_ABI

        if (length > 36) return CARD_INVALID;
#endif
        if (length < 6 || (reply[5] != 4 && reply[5] != 7 && reply[5] != 10)) return CARD_INVALID;
        at = 6 + reply[5];
        if (length < at) return CARD_INVALID;
#ifdef MG_UID_PROFILE
        if (!(reply[4] & 0x20)) {
            if (length != at) return CARD_INVALID;
            card->type = CARD_TYPE_STORAGE_A; card->cid = reply[5];
            copy_xdata(card->uid, reply + 6, reply[5]);
#ifdef MG_CH559_CLASSIC


            card->classic_candidate = reply[2] == 0 && reply[3] == 4 &&
                                      reply[4] == 8 && reply[5] == 4;
#ifdef MG_CLASSIC_7B
            if (reply[2] == 0 && reply[3] == 0x44 && reply[4] == 8 && reply[5] == 7)
                card->classic_candidate = 1;
#endif
#ifdef MG_CLASSIC_4K

            if (reply[2] == 0 && reply[3] == 2 && reply[4] == 0x18 && reply[5] == 4)
                card->classic_candidate = 2;
#ifdef MG_CLASSIC_7B
            if (reply[2] == 0 && reply[3] == 0x42 && reply[4] == 0x18 && reply[5] == 7)
                card->classic_candidate = 2;
#endif
#endif
#endif

            card->atr[4]=0x80; card->atr[5]=0x4f; card->atr[6]=0x0c;
            card->atr[7]=0xa0; card->atr[10]=3; card->atr[11]=6; card->atr[12]=3;
            historical=15; goto make_atr;
        }
#else
        if (!(reply[4] & 0x20)) return length == at ? CARD_UNSUPPORTED : CARD_INVALID;
#endif

        if (length < at + 2 || reply[at] < 2 || length != at + reply[at]) return CARD_INVALID;
        end = length; t0 = reply[at + 1];
        if ((t0 & 0x80) || (t0 & 15) > 8) return CARD_INVALID;
        at += 2;
        if (t0 & 0x10) {
            if (at >= end || (reply[at] & 8)) return CARD_INVALID;
            ++at;
        }
        if (t0 & 0x20) {
            if (at >= end || (reply[at] >> 4) == 15 || (reply[at] & 15) == 15) return CARD_INVALID;
            ++at;
        }
        if (t0 & 0x40) {
            if (at >= end || (reply[at] & 0xfc)) return CARD_INVALID;
            ++at;
        }
        if (at > end || end - at > 15) return CARD_INVALID;
        historical = end - at;
#ifdef MG_UID_PROFILE
        copy_xdata(card->atr + 4, reply + at, historical);
#else
        for (i = 0; i < historical; ++i) card->atr[4 + i] = reply[at + i];
#endif
#endif
    } else if (type == CARD_TYPE_B) {
        if (length < 16 || reply[2] != 0x50 || !reply[14] || length != 15u + reply[14])
            return CARD_INVALID;

        if ((reply[12] & 15) != 1) return CARD_UNSUPPORTED;
        if ((reply[12] >> 4) > 8 || (reply[15] & 15) == 15) return CARD_INVALID;
        card->cid = reply[15] & 15;
        historical = 8;
#ifdef MG_UID_PROFILE
        copy_xdata(card->atr + 4, reply + 7, 7);
#else
        for (i = 0; i < 7; ++i) card->atr[4 + i] = reply[7 + i];
#endif
        card->atr[11] = reply[15] & 0xf0;
#ifdef MG_CH559_FELICA
    } else if (type == CARD_SCAN_F) {

        if ((length != 20 && length != 22) || reply[2] != length-2 || reply[3] != 1)
            return CARD_INVALID;
        card->type=CARD_TYPE_STORAGE_F; card->cid=8;
        copy_xdata(card->uid,reply+4,8);
        card->atr[4]=0x80; card->atr[5]=0x4f; card->atr[6]=0x0c;
        card->atr[7]=0xa0; card->atr[10]=3; card->atr[11]=6; card->atr[12]=0x11;
        historical=15; goto make_atr;
#endif
    } else return CARD_INVALID;
#ifdef MG_UID_PROFILE
make_atr:
#endif
    card->atr[0] = 0x3b; card->atr[1] = 0x80 | historical;
    card->atr[2] = 0x80; card->atr[3] = 1;
    sum = 0;
    for (i = 1; i < 4 + historical; ++i) sum ^= card->atr[i];
    card->atr[4 + historical] = sum;
    card->atr_length = 5 + historical;
#ifdef MG_UID_PROFILE
    if (card->type != CARD_TYPE_STORAGE_A
#ifdef MG_CH559_FELICA
        && card->type != CARD_TYPE_STORAGE_F
#endif
        ) card->type = type;
#else
    card->type = type;
#endif
    return CARD_FOUND;
}
#ifndef MG_RAW_B_COMPARE
uint8_t card_short_apdu(const uint8_t __xdata *MG_LOCAL data, uint16_t MG_LOCAL length) MG_CALL {
    if (length < 4 || length > 261) return 0;
    if (length <= 5) return 1;
    if (!data[4]) return 0;
    return length == (uint16_t)data[4] + 5 || length == (uint16_t)data[4] + 6;
}

#endif
