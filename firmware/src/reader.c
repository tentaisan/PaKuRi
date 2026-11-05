/* SPDX-License-Identifier: Apache-2.0 */
/* ManeKey reader.rsの初期化・接続無効化・単発APDUを2026-10-25に翻案。
 * A/B scan・PCSC ATR・非破壊在席確認・共有buffer配置はPaKuRi用。 */
#include "reader.h"
#include "events.h"
#ifdef MG_CH559_FELICA
#include "../experimental/felica/read.h"
static __xdata FRead felica_read;
static __xdata int felica_result;
static __xdata uint8_t felica_error;
#endif
#ifdef MG_CH559_CLASSIC
#include "../experimental/mifare/classic.h"
#ifdef __SDCC
static __xdata McSession classic_session;
#else
__xdata McSession classic_session;
#endif
static __xdata uint8_t classic_buffer[32];
static __xdata size_t classic_length;
static __xdata uint16_t classic_deadline;
static __xdata int classic_result;
static __xdata uint8_t classic_error, classic_bad;

static void classic_clear(void) {
    mc_clear(&classic_session);
    wipe_xdata(classic_buffer,sizeof(classic_buffer));
    classic_length=0; classic_deadline=0;
}

uint8_t reader_classic_held(uint16_t MG_LOCAL now) {
    if (!classic_session.key_loaded) return 0;
    if ((int16_t)(now-classic_deadline)>=0) { classic_clear(); return 0; }
    return 1;
}
#endif
#ifdef MG_SOFT_B
#ifndef MG_SINGLETON
#error software Type B requires the single-reader profile
#endif
#include "isodep_b.h"
static __xdata uint16_t b_deadline;
#endif
#ifdef MG_SINGLETON

__xdata Reader reader_state;
#define R(r) (&reader_state)
#ifdef MG_COMPACT_ABI
#define VALID_READER(r) 1
#else
#define VALID_READER(r) ((r) == &reader_state)
#endif
#define PRIVATE_READER_PARAM
#define PRIVATE_READER_ONLY_PARAM void
#define PRIVATE_READER_ARG
#define PRIVATE_READER_ONLY_ARG
#else
#define R(r) (r)
#define VALID_READER(r) 1
#define PRIVATE_READER_PARAM Reader __xdata *r,
#define PRIVATE_READER_ONLY_PARAM Reader __xdata *r
#define PRIVATE_READER_ARG r,
#define PRIVATE_READER_ONLY_ARG r
#endif

#ifdef MG_SCAN_DIAGNOSTIC
volatile __xdata uint8_t reader_scan_diagnostic[7];
#endif

static void invalidate(PRIVATE_READER_ONLY_PARAM) MG_CALL {
#ifdef MG_CH559_FELICA
    fr_clear(&felica_read);
#endif
#ifdef MG_CH559_CLASSIC
    classic_clear();
#endif
#ifdef MG_SOFT_B
    depb_clear(&depb_state);R(r)->activate=0;
#endif
    R(r)->present = R(r)->active = R(r)->selected = 0;
    card_clear(&R(r)->card);
}
static void failed(PRIVATE_READER_PARAM uint8_t error) MG_CALL {
#if defined(MG_EVENTS) && defined(MG_SINGLETON)
    if (R(r)->phase != READER_FAILED) mg_events_publish(MG_EVENT_READER_FAILED);
#endif
    invalidate(PRIVATE_READER_ONLY_ARG); R(r)->initialized = 0; R(r)->error = error; R(r)->phase = READER_FAILED;
}
#ifdef MG_UID_PROFILE
#define NEXT_PARAM , uint8_t next
#define NEXT_ARG(value) , (value)
#define NEXT_ASSIGN(value) ((void)0)
#else
#define NEXT_PARAM
#define NEXT_ARG(value)
#define NEXT_ASSIGN(value) (R(r)->phase = (value))
#endif
static uint8_t begin(PRIVATE_READER_PARAM uint8_t command, uint8_t count,
    uint16_t bound, uint16_t now NEXT_PARAM) MG_CALL {
    uint8_t error = pn_transport_begin(&R(r)->pn, command, R(r)->pn.frame + 7, count, bound, now, 1000);
    if (error) failed(PRIVATE_READER_ARG  error);
#ifdef MG_UID_PROFILE
    else R(r)->phase=next;
#endif
    return error;
}
#ifdef MG_SOFT_B
static uint8_t send_b(uint16_t now) MG_CALL {
    uint16_t count;
    int16_t remaining=(int16_t)(b_deadline-now);
    uint8_t error;
    if (remaining<=0) { failed(PN_ERR_TIMEOUT);return READER_LINK; }

    count=depb_next(&depb_state,R(r)->pn.frame+10);
    if (!count) { failed(READER_BAD_CARD);return READER_LINK; }
    error=pn_transport_begin(&R(r)->pn,0x42,R(r)->pn.frame+10,count,63,now,remaining);
    if (error) { failed(error);return READER_LINK; }
    return READER_OK;
}
#endif
void MG_ENTRY(reader_recover)(MG_SELF_PARAM(Reader, r) uint16_t now) MG_CALL {
    if (!VALID_READER(r)) return;
    invalidate(PRIVATE_READER_ONLY_ARG); R(r)->initialized = 0; R(r)->error = READER_OK;
    R(r)->rf_status = 0xff;
    pn_transport_recover(&R(r)->pn, now); R(r)->phase = READER_RECOVER;
}
void MG_ENTRY(reader_init)(MG_SELF_PARAM(Reader, r) uint16_t now) MG_CALL {
    if (!VALID_READER(r)) return;
#ifdef MG_SCAN_DIAGNOSTIC
    reader_scan_diagnostic[0] = 0;
    reader_scan_diagnostic[1] = reader_scan_diagnostic[6] = 0xff;
    reader_scan_diagnostic[2] = reader_scan_diagnostic[3] = 0;
    reader_scan_diagnostic[4] = reader_scan_diagnostic[5] = 0;
#endif
    pn_transport_init(&R(r)->pn); R(r)->scan_type = R(r)->activate = 0;
    reader_recover(MG_OWNER(r, R(r)), now);
}
void MG_ENTRY(reader_release)(MG_SELF_ONLY(Reader, r)) MG_CALL {
    if (!VALID_READER(r)) return;
    if (R(r)->phase != READER_DONE) return;
#ifdef MG_SOFT_B
    depb_clear(&depb_state);
#endif
    pn_transport_release(&R(r)->pn);
#ifdef MG_CH559_CLASSIC
    if (R(r)->pn.phase == PN_READY) wipe_xdata(R(r)->pn.frame,PN532_FRAME_MAX);
#endif
    R(r)->error = READER_OK; R(r)->phase = READER_IDLE;
}
uint8_t MG_ENTRY(reader_scan)(MG_SELF_PARAM(Reader, r) uint8_t type, uint8_t activate, uint16_t now) MG_CALL {
    if (!VALID_READER(r)) return READER_BUSY;
    if (R(r)->phase != READER_IDLE || !R(r)->initialized || R(r)->active) return READER_BUSY;
    if (type != CARD_TYPE_A && type != CARD_TYPE_B
#ifdef MG_CH559_FELICA
        && type != CARD_SCAN_F
#endif
        ) return READER_BAD_CARD;
    invalidate(PRIVATE_READER_ONLY_ARG); R(r)->scan_type = type; R(r)->activate = activate != 0;
    R(r)->pn.frame[7] = 1; R(r)->pn.frame[8] = type; R(r)->pn.frame[9] = 0;
#ifdef MG_CH559_FELICA
    if (type == CARD_SCAN_F) {
        R(r)->pn.frame[10]=0xff; R(r)->pn.frame[11]=0xff;
        R(r)->pn.frame[12]=R(r)->pn.frame[13]=0;
    }
    if (begin(PRIVATE_READER_ARG 0x4a, type == CARD_TYPE_A ? 2 : (type == CARD_SCAN_F ? 7 : 3), 263, now NEXT_ARG(READER_SCAN))) return READER_LINK;
#else
    if (begin(PRIVATE_READER_ARG 0x4a, type == CARD_TYPE_A ? 2 : 3, 263, now NEXT_ARG(READER_SCAN))) return READER_LINK;
#endif
    NEXT_ASSIGN(READER_SCAN); return READER_OK;
}
uint8_t MG_ENTRY(reader_presence)(MG_SELF_PARAM(Reader, r) uint16_t now) MG_CALL {
    uint8_t count = 1;
    if (!VALID_READER(r)) return READER_BUSY;
    if (R(r)->phase != READER_IDLE || !R(r)->initialized || !R(r)->selected) return READER_BUSY;
#ifdef MG_CH559_FELICA
    fr_clear(&felica_read);
#endif
#ifdef MG_CH559_CLASSIC
    classic_clear();
#endif
#ifdef MG_UID_PROFILE
#ifdef MG_CH559_FELICA
    if (R(r)->card.type == CARD_TYPE_STORAGE_F) {
        R(r)->pn.frame[7]=1;
        if (begin(PRIVATE_READER_ARG 0x52,1,1,now NEXT_ARG(READER_FELICA_RELEASE))) return READER_LINK;
        return READER_OK;
    }
#endif
    if (R(r)->card.type == CARD_TYPE_STORAGE_A) {
        R(r)->pn.frame[7]=1;
        if (begin(PRIVATE_READER_ARG 0x44,1,1,now NEXT_ARG(READER_STORAGE_DESELECT))) return READER_LINK;
        return READER_OK;
    }
#endif

    R(r)->pn.frame[7] = 0xb2;
    if (R(r)->card.type == CARD_TYPE_B) {
#ifdef MG_SOFT_B
        R(r)->pn.frame[7]|=R(r)->activate;
        if (R(r)->card.cid) {
            R(r)->pn.frame[7]|=8;R(r)->pn.frame[8]=R(r)->card.cid;++count;
        }
#else
        R(r)->pn.frame[7] = 0xba; R(r)->pn.frame[8] = R(r)->card.cid; ++count;
#endif
    }
    if (begin(PRIVATE_READER_ARG 0x42, count, 263, now NEXT_ARG(READER_PRESENCE))) return READER_LINK;
    NEXT_ASSIGN(READER_PRESENCE); return READER_OK;
}
uint8_t MG_ENTRY(reader_field_off)(MG_SELF_PARAM(Reader, r) uint16_t now) MG_CALL {
    if (!VALID_READER(r)) return READER_BUSY;
    if (R(r)->phase != READER_IDLE || !R(r)->initialized) return READER_BUSY;
#ifdef MG_CH559_FELICA
    fr_clear(&felica_read);
#endif
#ifdef MG_CH559_CLASSIC
    classic_clear();
#endif
    R(r)->active = R(r)->selected = 0;
#ifdef MG_SOFT_B
    depb_clear(&depb_state);R(r)->activate=0;
#endif
    R(r)->pn.frame[7] = 1; R(r)->pn.frame[8] = 0;
    if (begin(PRIVATE_READER_ARG 0x32, 2, 0, now NEXT_ARG(READER_OFF))) return READER_LINK;
    NEXT_ASSIGN(READER_OFF); return READER_OK;
}
#ifdef MG_CH559_FELICA
uint8_t reader_felica_exchange(const uint8_t __xdata *MG_LOCAL data, uint16_t MG_LOCAL length, uint16_t MG_LOCAL now) {
    if (R(0)->phase != READER_IDLE || !R(0)->initialized || !R(0)->active ||
        !R(0)->selected || R(0)->card.type != CARD_TYPE_STORAGE_F) return READER_BUSY;
    felica_result=fr_begin(&felica_read,R(0)->card.uid,data,length);
    if (felica_result != FR_EXCHANGE) {
        fr_clear(&felica_read);wipe_xdata(R(0)->pn.frame,PN532_FRAME_MAX);
        R(0)->pn.frame[0]=0x6a;R(0)->pn.frame[1]=0x80;
        R(0)->pn.offset=0;R(0)->pn.payload=2;R(0)->phase=READER_DONE;
        return READER_OK;
    }
    felica_error=pn_transport_begin(&R(0)->pn,0x40,felica_read.command,
                                    felica_read.command_length,142,now,15000);
    wipe_xdata(felica_read.command,sizeof(felica_read.command));felica_read.command_length=0;
    if (felica_error) { fr_clear(&felica_read);failed(felica_error);return READER_LINK; }
    R(0)->active=0;R(0)->phase=READER_FELICA;return READER_OK;
}
#endif
#ifdef MG_CH559_CLASSIC
#ifdef MG_CLASSIC_7B
#define CLASSIC_UID_LENGTH R(0)->card.cid
#else
#define CLASSIC_UID_LENGTH 4
#endif
uint8_t reader_classic_exchange(const uint8_t __xdata *MG_LOCAL data, uint16_t MG_LOCAL length, uint16_t MG_LOCAL now) {
    if (R(0)->phase != READER_IDLE || !R(0)->initialized || !R(0)->active ||
        !R(0)->selected || !R(0)->card.classic_candidate) return READER_BUSY;
    (void)reader_classic_held(now);
    if (!classic_session.present && !(
#ifdef MG_CLASSIC_4K
        R(0)->card.classic_candidate == 2 ? mc_attach_4k(&classic_session,R(0)->card.uid,CLASSIC_UID_LENGTH) :
#endif
        mc_attach(&classic_session,R(0)->card.uid,CLASSIC_UID_LENGTH))) {
        wipe_xdata(R(0)->pn.frame,PN532_FRAME_MAX); return READER_BAD_CARD;
    }
    classic_result=mc_command(&classic_session,data,length,classic_buffer,sizeof(classic_buffer),&classic_length);
    if (classic_result == MC_RESPONSE) {
        wipe_xdata(R(0)->pn.frame,PN532_FRAME_MAX);
        copy_xdata(R(0)->pn.frame,classic_buffer,classic_length);
        R(0)->pn.offset=0; R(0)->pn.payload=classic_length;
        wipe_xdata(classic_buffer,sizeof(classic_buffer)); classic_length=0;
        if (classic_session.key_loaded) classic_deadline=now+15000;
        R(0)->phase=READER_DONE; return READER_OK;
    }
    if (classic_result != MC_EXCHANGE) {
        wipe_xdata(R(0)->pn.frame,PN532_FRAME_MAX); classic_clear(); return READER_BAD_APDU;
    }
    classic_error=pn_transport_begin(&R(0)->pn,0x40,classic_buffer,classic_length,17,now,15000);
    wipe_xdata(classic_buffer,sizeof(classic_buffer)); classic_length=0;
    if (classic_error) { classic_clear(); failed(classic_error); return READER_LINK; }
    classic_deadline=now+15000; R(0)->active=0; R(0)->phase=READER_CLASSIC;
    return READER_OK;
}
#endif
uint8_t MG_ENTRY(reader_exchange)(MG_SELF_PARAM(Reader, r) const uint8_t __xdata *data,
    uint16_t length, uint16_t now) MG_CALL {
    if (!VALID_READER(r)) return READER_BUSY;
#ifdef MG_SCAN_DIAGNOSTIC

    (void)data; (void)length; (void)now;
    return READER_BAD_APDU;
#else
#if !defined(MG_UID_PROFILE) || defined(MG_RAW_B_COMPARE)
    uint16_t i;
#endif
    uint8_t error;
#ifndef MG_RAW_B_COMPARE
    uint8_t at;
#endif
    if (R(r)->phase != READER_IDLE || !R(r)->initialized || !R(r)->active || !R(r)->selected)
        return READER_BUSY;
#ifdef MG_RAW_B_COMPARE

    if (!R(r)->activate || R(r)->card.type != CARD_TYPE_B || R(r)->card.cid != 1 ||
#ifdef MG_RAW_B_TIMED
        R(r)->card.atr[9] != 0x81 || (R(r)->card.atr[10] >> 4) != 10 ||
#endif
#ifdef MG_RAW_B_CONTROL
        (length != 22 && length != 118) ||
        data[0] || data[1] != 0xa4 || data[2] != 4 || data[3] || data[4] != length - 6)
#else
        length != 118 ||
        data[0] || data[1] != 0xa4 || data[2] != 4 || data[3] || data[4] != 112)
#endif
        return READER_BAD_APDU;
    for (i = 5; i < length; ++i) if (data[i]) return READER_BAD_APDU;
    for (i = 0; i < length; ++i) R(r)->pn.frame[9 + i] = data[i];
    R(r)->pn.frame[7] = 0x0a; R(r)->pn.frame[8] = 1;
    R(r)->activate = 0;
#ifdef MG_RAW_B_CONTROL
    error = pn_transport_begin(&R(r)->pn, 0x42, R(r)->pn.frame + 7, length + 2, 263, now, 15000);
#else
    error = pn_transport_begin(&R(r)->pn, 0x42, R(r)->pn.frame + 7, 120, 263, now, 15000);
#endif
#else
    if (!card_short_apdu(data, length)) return READER_BAD_APDU;
#ifdef MG_SOFT_B
    if (R(r)->card.type==CARD_TYPE_B) {
        if (depb_begin(&depb_state,data,length,R(r)->card.atr[9]>>4,R(r)->card.cid)) {
            failed(READER_BAD_APDU);return READER_LINK;
        }
        depb_state.block=R(r)->activate;
        b_deadline=now+15000;
        error=send_b(now);
        if (error) return READER_LINK;
    } else {
#endif
    at = length + 3 > 255 ? 10 : 7;
#ifdef MG_UID_PROFILE
    copy_xdata(R(r)->pn.frame+at+1,data,length);
#else
    for (i = 0; i < length; ++i) R(r)->pn.frame[at + 1 + i] = data[i];
#endif
    R(r)->pn.frame[at] = 1;
    error = pn_transport_begin(&R(r)->pn, 0x40, R(r)->pn.frame + at, length + 1, 259, now, 15000);
#ifdef MG_SOFT_B
    }
#endif
#endif
    if (error) { failed(PRIVATE_READER_ARG  error); return READER_LINK; }
    R(r)->active = 0;
    R(r)->phase = READER_APDU; return READER_OK;
#endif
}
void MG_ENTRY(reader_poll)(MG_SELF_PARAM(Reader, r) uint16_t now) MG_CALL {
    if (!VALID_READER(r)) return;
    uint8_t error;
    uint8_t __xdata *payload;
    if (R(r)->phase == READER_FAILED || R(r)->phase == READER_CLOSED) return;
    pn_transport_poll(&R(r)->pn, now);
    if (R(r)->pn.phase == PN_FAILED) { failed(PRIVATE_READER_ARG  R(r)->pn.error); return; }
    if (R(r)->phase == READER_RECOVER) {
        if (R(r)->pn.phase == PN_READY) {
            if ((R(r)->pn.support & 3) != 3) { failed(PRIVATE_READER_ARG  READER_BAD_CARD); return; }
            R(r)->pn.frame[7] = 1; R(r)->pn.frame[8] = R(r)->pn.frame[9] = 0;
            if (begin(PRIVATE_READER_ARG 0x14, 3, 0, now NEXT_ARG(READER_SAM))) return;
            NEXT_ASSIGN(READER_SAM);
        }
        return;
    }
    if (R(r)->phase == READER_DONE || R(r)->phase == READER_IDLE || R(r)->pn.phase != PN_DONE) return;
    payload = R(r)->pn.frame + R(r)->pn.offset;
#if defined(MG_RF_WAIT) || defined(MG_SOFT_B)
    if ((uint8_t)(R(r)->phase - READER_SAM) <= READER_RETRIES - READER_SAM ||
        R(r)->phase == READER_OFF || R(r)->phase == READER_RAW_TIMINGS) {
#else
    if (R(r)->phase == READER_SAM || R(r)->phase == READER_PARAMETERS || R(r)->phase == READER_RETRIES || R(r)->phase == READER_OFF
#if defined(MG_RAW_B_TIMED) || defined(MG_RF_WAIT)
        || R(r)->phase == READER_RAW_TIMINGS
#endif
        ) {
#endif
        if (R(r)->pn.payload) { failed(PRIVATE_READER_ARG  READER_BAD_CARD); return; }
        if (R(r)->phase == READER_SAM) {
            pn_transport_release(&R(r)->pn); R(r)->pn.frame[7] = 0x14;
            if (begin(PRIVATE_READER_ARG 0x12, 1, 0, now NEXT_ARG(READER_PARAMETERS))) return;
            NEXT_ASSIGN(READER_PARAMETERS); return;
        }
#if defined(MG_RF_WAIT) || defined(MG_SOFT_B)
        if (R(r)->phase == READER_PARAMETERS || R(r)->phase == READER_RAW_TIMINGS) {
            pn_transport_release(&R(r)->pn);
            R(r)->pn.frame[7] = 5;
            R(r)->pn.frame[8] = R(r)->pn.frame[9] = R(r)->pn.frame[10] = 0;
            if (R(r)->phase == READER_PARAMETERS) {
                R(r)->pn.frame[7] = 2; R(r)->pn.frame[9] = 0x0b;
#ifdef MG_RF_WAIT
                R(r)->pn.frame[10] = 0x0d;
#endif
            }
            if (begin(PRIVATE_READER_ARG 0x32, 4, 0, now NEXT_ARG(R(r)->phase == READER_PARAMETERS ? READER_RAW_TIMINGS : READER_RETRIES))) return;
            NEXT_ASSIGN(R(r)->phase == READER_PARAMETERS ? READER_RAW_TIMINGS : READER_RETRIES);
            return;
        }
#else
#ifdef MG_RAW_B_TIMED
        if (R(r)->phase == READER_PARAMETERS) {
            pn_transport_release(&R(r)->pn);


            R(r)->pn.frame[7] = 2; R(r)->pn.frame[8] = 0;
            R(r)->pn.frame[9] = 0x0b; R(r)->pn.frame[10] = 0x0d;
            if (begin(PRIVATE_READER_ARG 0x32, 4, 0, now NEXT_ARG(READER_RAW_TIMINGS))) return;
            NEXT_ASSIGN(READER_RAW_TIMINGS); return;
        }
        if (R(r)->phase == READER_RAW_TIMINGS) {
#else
        if (R(r)->phase == READER_PARAMETERS) {
#endif
            pn_transport_release(&R(r)->pn);
            R(r)->pn.frame[7] = 5; R(r)->pn.frame[8] = R(r)->pn.frame[9] = R(r)->pn.frame[10] = 0;
            if (begin(PRIVATE_READER_ARG 0x32, 4, 0, now NEXT_ARG(READER_RETRIES))) return;
            NEXT_ASSIGN(READER_RETRIES); return;
        }
#endif
        R(r)->initialized = 1;
    } else if (R(r)->phase == READER_SCAN) {
        error = card_parse(&R(r)->card, R(r)->scan_type, payload, R(r)->pn.payload);
#ifdef MG_SCAN_DIAGNOSTIC


        ++reader_scan_diagnostic[0];
        if (R(r)->scan_type == CARD_TYPE_A) {
            reader_scan_diagnostic[1] = error;
            reader_scan_diagnostic[2] = reader_scan_diagnostic[3] = 0;
            reader_scan_diagnostic[4] = reader_scan_diagnostic[5] = 0;
            if (error == CARD_FOUND || error == CARD_UNSUPPORTED) {
                reader_scan_diagnostic[2] = payload[2];
                reader_scan_diagnostic[3] = payload[3];
                reader_scan_diagnostic[4] = payload[4];
                reader_scan_diagnostic[5] = payload[5];
            }
        } else reader_scan_diagnostic[6] = error;
        ++reader_scan_diagnostic[0];
#endif
        if (error == CARD_INVALID) { failed(PRIVATE_READER_ARG  READER_BAD_CARD); return; }
        R(r)->present = R(r)->selected = error == CARD_FOUND;
        R(r)->active = R(r)->present && R(r)->activate;
#ifdef MG_SOFT_B
        R(r)->activate=0;
#endif
        R(r)->error = R(r)->present ? READER_OK : READER_ABSENT;
#ifdef MG_CH559_FELICA
    } else if (R(r)->phase == READER_FELICA_RELEASE) {
        if (R(r)->pn.payload != 1) { failed(READER_BAD_CARD);return; }
        R(r)->rf_status=payload[0];
        if (payload[0]) { invalidate();R(r)->error=READER_ABSENT; }
        else {
            pn_transport_release(&R(r)->pn);
            R(r)->pn.frame[7]=1;R(r)->pn.frame[8]=CARD_SCAN_F;R(r)->pn.frame[9]=0;
            R(r)->pn.frame[10]=R(r)->pn.frame[11]=0xff;
            R(r)->pn.frame[12]=R(r)->pn.frame[13]=0;
            if (begin(0x4a,7,22,now NEXT_ARG(READER_FELICA_PRESENCE))) return;
            return;
        }
    } else if (R(r)->phase == READER_FELICA_PRESENCE) {
        if (R(r)->pn.payload == 1 && payload[0] == 0) {
            invalidate();R(r)->error=READER_ABSENT;
        } else {
            uint8_t MG_LOCAL same=1, j;
            if ((R(r)->pn.payload!=20 && R(r)->pn.payload!=22) || payload[0]!=1 ||
                payload[1]!=1 || payload[2]!=R(r)->pn.payload-2 || payload[3]!=1) {
                failed(READER_BAD_CARD);return;
            }
            for (j=0;j<8;++j) if (payload[4+j]!=R(r)->card.uid[j]) same=0;
            if (!same) {
                invalidate();R(r)->error=READER_ABSENT;


                pn_transport_release(&R(r)->pn);R(r)->pn.frame[7]=1;
                if (begin(0x52,1,1,now NEXT_ARG(READER_FELICA_DROP))) return;
                return;
            }
        }
    } else if (R(r)->phase == READER_FELICA_DROP) {
        if (R(r)->pn.payload!=1 || payload[0]) { failed(READER_BAD_CARD);return; }
#endif
    } else if (R(r)->phase == READER_PRESENCE
#ifdef MG_UID_PROFILE
        || R(r)->phase == READER_STORAGE_DESELECT
#endif
        ) {
        if (!R(r)->pn.payload) { failed(PRIVATE_READER_ARG  READER_BAD_CARD); return; }
#ifdef MG_UID_PROFILE
        if (R(r)->card.type == CARD_TYPE_STORAGE_A && R(r)->pn.payload != 1) { failed(PRIVATE_READER_ARG READER_BAD_CARD); return; }
#endif
        R(r)->rf_status = payload[0];
        if (R(r)->rf_status) { invalidate(PRIVATE_READER_ONLY_ARG); R(r)->error = READER_ABSENT; }
#ifdef MG_UID_PROFILE
        else if (R(r)->card.type == CARD_TYPE_STORAGE_A) {
            if (R(r)->phase == READER_STORAGE_DESELECT) {
                pn_transport_release(&R(r)->pn); R(r)->pn.frame[7]=1;
                if (begin(PRIVATE_READER_ARG 0x54,1,1,now NEXT_ARG(READER_PRESENCE))) return;
                return;
            }
        }
#endif
        else {
            uint8_t pcb = payload[1];
            error = R(r)->card.type == CARD_TYPE_B
#ifdef MG_SOFT_B
                && R(r)->card.cid
#endif
                ? 3 : 2;
            if (R(r)->pn.payload < error || (pcb & 8) != (error == 3 ? 8 : 0) ||
                (error == 3 && payload[2] != R(r)->card.cid) ||
                !((pcb & 0xe6) == 2 || ((pcb & 0xf6) == 0xa2 && R(r)->pn.payload == error))) {
                failed(PRIVATE_READER_ARG  READER_BAD_CARD); return;
            }
        }
#ifdef MG_CH559_FELICA
    } else if (R(r)->phase == READER_FELICA) {
        felica_result=fr_complete(&felica_read,payload,R(r)->pn.payload);
        pn_transport_release(&R(r)->pn);
        if (felica_result != FR_RESPONSE) { fr_clear(&felica_read);failed(READER_BAD_CARD);return; }
        copy_xdata(R(r)->pn.frame,felica_read.response,felica_read.response_length);
        R(r)->pn.offset=0;R(r)->pn.payload=felica_read.response_length;
        fr_clear(&felica_read);R(r)->active=1;
#endif
#ifdef MG_CH559_CLASSIC
    } else if (R(r)->phase == READER_CLASSIC) {
        classic_result=mc_complete(&classic_session,payload,R(r)->pn.payload,
                                   classic_buffer,sizeof(classic_buffer),&classic_length);
        classic_bad=!R(r)->pn.payload || payload[0] ||
                    (classic_length==2 && classic_buffer[0]==0x63);
        pn_transport_release(&R(r)->pn);
        if (classic_result != MC_RESPONSE || classic_length > sizeof(classic_buffer)) {
            classic_clear(); failed(READER_BAD_CARD); return;
        }
        copy_xdata(R(r)->pn.frame,classic_buffer,classic_length);
        R(r)->pn.offset=0; R(r)->pn.payload=classic_length;
        wipe_xdata(classic_buffer,sizeof(classic_buffer)); classic_length=0;
        if (classic_bad) classic_clear(); else classic_deadline=now+15000;
        R(r)->active=1;
#endif
    } else if (R(r)->phase == READER_APDU) {


        R(r)->rf_status = R(r)->pn.payload ? payload[0] : 0xff;
#ifdef MG_RAW_B_COMPARE
        if (R(r)->pn.payload != 5 || payload[0] || payload[1] != 0x0a || payload[2] != 1) {
            failed(PRIVATE_READER_ARG  READER_BAD_CARD); return;
        }
        R(r)->pn.offset += 3; R(r)->pn.payload -= 3; R(r)->active = 1;
#else
#ifdef MG_SOFT_B
        if (R(r)->card.type==CARD_TYPE_B) {
            if (!R(r)->pn.payload || payload[0] || depb_receive(&depb_state,payload+1,R(r)->pn.payload-1)) {
                failed(READER_BAD_CARD);return;
            }
            if (depb_state.phase!=DEPB_DONE) {
                pn_transport_release(&R(r)->pn);send_b(now);return;
            }
            R(r)->activate=depb_state.block;
#ifdef MG_UID_PROFILE
            copy_xdata(R(r)->pn.frame,depb_state.buffer,depb_state.used);
#else
            for (R(r)->pn.offset=0;R(r)->pn.offset<depb_state.used;++R(r)->pn.offset)
                R(r)->pn.frame[R(r)->pn.offset]=depb_state.buffer[R(r)->pn.offset];
#endif
            R(r)->pn.offset=0;R(r)->pn.payload=depb_state.used;R(r)->active=1;
        } else {
#endif
        if (R(r)->pn.payload < 3 || R(r)->pn.payload > 259 || payload[0]) {
            failed(PRIVATE_READER_ARG  READER_BAD_CARD); return;
        }
        ++R(r)->pn.offset; --R(r)->pn.payload; R(r)->active = 1;
#ifdef MG_SOFT_B
        }
#endif
#endif
    }
    R(r)->phase = READER_DONE;
}
