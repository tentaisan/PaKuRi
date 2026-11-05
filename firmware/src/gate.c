/* SPDX-License-Identifier: AGPL-3.0-only */
/* CCID1.1に基づくPaKuRiの単一slot policy。ManeKeyのpacket/取消知見を使用。
 * PIN機能なし。Classic実験profile以外は鍵保持なし。APDUの再送なし。 */
#include "gate.h"
#include "events.h"
#define R reader_state
#define G gate_state
#define BODY_NONE 0
#define BODY_ATR 1
#define BODY_APDU 2
#define BODY_PARAMETERS 3
__xdata Gate gate_state;
static const __code uint8_t t1_parameters[7] = {0x11,0x10,0,0x4d,0,0xfe,0};
static const __code uint8_t fixed_rate[8] = {0xa0,0x0f,0,0,0x80,0x25,0,0};
#ifdef MG_CH559_CLASSIC
static void gate_release_out(void) {
    wipe_xdata(usb_ep2,64); usb_release_out();
}
#else
#define gate_release_out usb_release_out
#endif

static uint8_t status(void) {
    return G.slot || !R.present ? 2 : (G.powered ? 0 : 1);
}
static void notify(void) {
    if (!R.present) G.powered = 0;
    if (G.reported != R.present) {
        G.reported = R.present; usb_notify_slot(G.reported);
        mg_events_publish(G.reported ? MG_EVENT_CARD_PRESENT : MG_EVENT_CARD_ABSENT);
    }
}
static void reset_receive(void) {
    G.header_used = G.out_at = 0; G.body_length = G.body_received = 0;
}
static uint8_t response_type(void) {
    if (G.command == 0x62 || G.command == 0x6f || G.command == 0x69) return 0x80;
    if (G.command == 0x61 || G.command == 0x6c || G.command == 0x6d) return 0x82;
    if (G.command == 0x6b) return 0x83;
    if (G.command == 0x73) return 0x84;
    return 0x81;
}
static void reply(uint8_t error, MG_BOOL failed, uint8_t MG_LOCAL source, uint16_t MG_LOCAL length) {
#ifdef MG_UID_PROFILE
    uint8_t type = response_type();
    wipe_xdata(G.header,10);
#else
    uint8_t i, type = response_type();
    for (i = 0; i < 10; ++i) G.header[i] = 0;
#endif
    G.header[0] = type; G.header[1] = length; G.header[2] = length >> 8;
    G.header[5] = G.slot; G.header[6] = G.sequence;
    G.header[7] = status() | (G.interim ? 0x80 : (failed ? 0x40 : 0)); G.header[8] = error;
    G.header[9] = type == 0x82 ? 1 : (type == 0x81 && !G.powered ? 3 : 0);
    ccid_tx_init(&G.tx, length + 10, usb_ep2 + 64);
    G.source = source; G.response = 1;
    if (!G.interim) G.job = GATE_REPLY;
}
static void fail_reply(uint8_t error) {
#ifdef MG_CH559_CLASSIC

    if (G.command == 0x6f && R.phase == READER_IDLE && R.pn.phase == PN_READY)
        wipe_xdata(R.pn.frame,PN532_FRAME_MAX);
#endif
    if (G.command == 0x6f) mg_events_publish(MG_EVENT_EXCHANGE_FAILED);
    G.interim = 0; reply(error, 1, BODY_NONE, 0);
}
static void success(uint8_t source, uint16_t MG_LOCAL length) {
    if (G.command == 0x6f) mg_events_publish(MG_EVENT_EXCHANGE_DONE);
    G.interim = 0; reply(0, 0, source, length);
}
static void finish_reply(void) {
    G.response = 0;
    if (G.interim) { G.interim = 0; return; }
    if (G.source == BODY_APDU || G.source == BODY_ATR) reader_release(&R);
    G.active = G.bulk_first = 0; G.job = GATE_IDLE; reset_receive(); G.next_poll = G.now + 150;
}
static void send_reply(void) {
    uint16_t at, remaining;
    uint8_t count;
    const uint8_t __xdata *source;
    if (!G.response || !usb_bulk_ready()) return;
    if (!G.tx.waiting) {
        at = G.tx.copied;
        if (at < 10) {
            ccid_tx_push(&G.tx, G.header + at, 10 - at, usb_ep2 + 64);
        } else {
            at -= 10; remaining = G.tx.total - 10 - at;
            count = remaining > 54 ? 54 : remaining;
            if (G.source == BODY_ATR) source = R.card.atr;
            else if (G.source == BODY_APDU) source = R.pn.frame + R.pn.offset;
            else source = G.parameters;
            ccid_tx_push(&G.tx, source + at, count, usb_ep2 + 64);
        }
    }
    if (G.tx.waiting) usb_send_bulk(G.tx.used);
}
static void clean(uint16_t now) {
    if (G.active && G.command == 0x6f) mg_events_publish(MG_EVENT_EXCHANGE_CANCELLED);
    usb_cancel_bulk_in(); ccid_tx_stop(&G.tx, usb_ep2 + 64); gate_release_out();
    G.response = G.active = G.powered = G.background = G.bulk_first = 0;
    G.rx_closed = G.interim = 0; reset_receive(); G.job = GATE_IDLE;
    reader_recover(&R, now); notify();
}
#if !defined(MG_TIMING) && !defined(MG_UID_PROFILE)
static void remember_abort(uint8_t sequence) {

    usb_abort_snapshot[0] = sequence; usb_abort_snapshot[1] = R.phase;
    usb_abort_snapshot[2] = R.pn.phase;
}
#else
#define remember_abort(sequence) ((void)0)
#endif
static void start_abort(void) {
    uint8_t matched;
    if (G.aborting) return;
    matched = G.bulk_first && G.sequence == usb_abort_sequence && !G.slot;
    if (!matched) remember_abort(usb_abort_sequence);
    clean(G.now);
    G.aborting = 1; G.abort_matched = matched; G.abort_failed = 0;
    G.abort_deadline = G.now + 3000;
    if (matched) {
        G.command = 0x72; G.sequence = usb_abort_sequence; G.slot = 0;
        G.active = 1; G.job = GATE_ABORT;
    }
    usb_allow_abort_reply();
}
static void dispatch(void) {
    uint8_t i, error = 0;
    G.deadline = G.now + 15000; G.next_extension = G.now + 250;
    if (G.slot) { fail_reply(5); return; }
    if (G.aborting) {
        if (G.command == 0x72 && G.sequence == usb_abort_sequence && !G.body_length &&
            !(G.header[7] | G.header[8] | G.header[9])) {
            G.abort_matched = 1; G.job = GATE_ABORT; return;
        }
        fail_reply(0xff); return;
    }
    if (G.command != 0x61 && G.command != 0x6f && G.command != 0x73 && G.body_length) {
        fail_reply(1); return;
    }
    if (G.header[8] || G.header[9]) { fail_reply(8); return; }
    if (G.command != 0x62 && G.command != 0x61 && G.command != 0x6f && G.header[7]) {
        fail_reply(7); return;
    }
    if (G.command == 0x62) {
        if (G.header[7] > 1) { fail_reply(7); return; }
        G.startup_retry = 0;
        G.powered = 0; G.job = GATE_POWER_CLEAN;
        if (R.phase == READER_FAILED) reader_recover(&R, G.now);
    } else if (G.command == 0x6f) {
        if (G.header[7]) { fail_reply(7); return; }
        if (!G.powered || !R.active) { fail_reply(0xfe); return; }
        mg_events_publish(MG_EVENT_EXCHANGE_START);
#ifdef MG_UID_PROFILE
        if (R.card.type == CARD_TYPE_STORAGE_A
#ifdef MG_CH559_FELICA
            || R.card.type == CARD_TYPE_STORAGE_F
#endif
            ) {

            if (G.body_length != 5 || R.pn.frame[11] != 0xff || R.pn.frame[12] != 0xca ||
                R.pn.frame[13] || R.pn.frame[14]) {
#ifdef MG_CH559_FELICA
                if (R.card.type == CARD_TYPE_STORAGE_F && G.body_length>=5 &&
                    R.pn.frame[11]==0xff && R.pn.frame[12]==0xb0 &&
                    !R.pn.frame[13] && !R.pn.frame[14]) {
                    error=reader_felica_exchange(R.pn.frame+11,G.body_length,G.now);
                    if (error) fail_reply(error == READER_BAD_APDU ? 1 : 0xfb);
                    else G.job=GATE_EXCHANGE;
                    return;
                }
#endif
#ifdef MG_CH559_CLASSIC
                if (R.card.classic_candidate) {
                    error=reader_classic_exchange(R.pn.frame+11,G.body_length,G.now);
                    if (error) fail_reply(error == READER_BAD_APDU ? 1 : 0xfb);
                    else G.job=GATE_EXCHANGE;
                    return;
                }
#endif
                fail_reply(1); return;
            }
            i=R.pn.frame[15]; R.pn.offset=0;
            if (i && i<R.card.cid) { R.pn.frame[0]=0x6c; R.pn.frame[1]=R.card.cid; R.pn.payload=2; }
            else {
                if (!i) i=R.card.cid;
                wipe_xdata(R.pn.frame,(uint16_t)i+2); copy_xdata(R.pn.frame,R.card.uid,R.card.cid);
                R.pn.frame[i]=(i>R.card.cid)?0x62:0x90;
                R.pn.frame[(uint16_t)i+1]=(i>R.card.cid)?0x82:0;
                R.pn.payload=(uint16_t)i+2;
            }
            success(BODY_APDU,R.pn.payload); return;
        }
#endif
        error = reader_exchange(&R, R.pn.frame + 11, G.body_length, G.now);
        if (error) fail_reply(error == READER_BAD_APDU ? 1 : 0xfb);
        else G.job = GATE_EXCHANGE;
    } else if (G.command == 0x63) {
        G.powered = 0; G.job = GATE_OFF_START;
    } else if (G.command == 0x65 || G.command == 0x6e) success(BODY_NONE, 0);
    else if (G.command == 0x6c || G.command == 0x6d || G.command == 0x61) {
        if (G.command == 0x61) {
            if (G.body_length != 7) error = 1;
            else if (G.header[7] != 1) error = 7;
            else for (i = 0; i < 7; ++i) if (G.parameters[i] != t1_parameters[i]) { error = 10 + i; break; }
        }
        if (error) fail_reply(error);
        else { for (i = 0; i < 7; ++i) G.parameters[i] = t1_parameters[i]; success(BODY_PARAMETERS, 7); }
    } else if (G.command == 0x73) {
        if (G.body_length != 8) error = 1;
        else for (i = 0; i < 8; ++i) if (G.parameters[i] != fixed_rate[i]) { error = i < 4 ? 10 : 14; break; }
        if (error) fail_reply(error);
        else success(BODY_PARAMETERS, 8);
    } else if (G.command == 0x72) {
        remember_abort(G.sequence);
        G.bulk_first = 1; G.job = GATE_ABORT; G.deadline = G.now + 3000;
    } else fail_reply(0);
}
static void receive(void) {
    uint8_t byte, count = 0;

    if (usb_out_pending && !G.rx_closed && G.active && G.job != GATE_RECEIVE &&
        !G.slot && usb_out_length == 10 &&
        usb_ep2[0] == 0x72 && usb_ep2[6] == G.sequence) {
        for (byte = 1; byte < 10; ++byte) if (byte != 6 && usb_ep2[byte]) return;
        if (G.bulk_first || G.command == 0x72) { gate_release_out(); return; }
        if (G.aborting) return;
        remember_abort(G.sequence);
        clean(G.now); G.command = 0x72; G.bulk_first = G.active = 1;
        G.job = GATE_ABORT; G.deadline = G.now + 3000; return;
    }
    if (!usb_out_pending || G.response || G.rx_closed || (G.active && G.job != GATE_RECEIVE)) return;
    if (!G.header_used) { G.deadline = G.now + 1000; G.job = GATE_RECEIVE; }
    while (G.out_at < usb_out_length && count++ < 64) {
        if (G.header_used == 10 && G.command == 0x6f && G.powered && G.background) return;
#ifdef MG_CH559_CLASSIC
        byte = usb_ep2[G.out_at]; usb_ep2[G.out_at++] = 0;
#else
        byte = usb_ep2[G.out_at++];
#endif
        if (G.header_used < 10) {
            G.header[G.header_used++] = byte;
            if (G.header_used == 10) {
                G.command = G.header[0]; G.slot = G.header[5]; G.sequence = G.header[6]; G.active = 1;
                G.body_length = (uint16_t)G.header[1] | ((uint16_t)G.header[2] << 8);
                if (G.header[3] || G.header[4] || G.body_length > 261) {
                    G.rx_closed = 1; gate_release_out(); G.out_at = 0; fail_reply(1); return;
                }
            }
        } else {
            if (G.body_received >= G.body_length) { G.rx_closed = 1; fail_reply(1); break; }
            if (G.command == 0x6f && !G.slot && !G.aborting && G.powered && R.phase == READER_IDLE && R.active)
                R.pn.frame[11 + G.body_received] = byte;
            if ((G.command == 0x61 || G.command == 0x73) && G.body_received < 8)
                G.parameters[G.body_received] = byte;
            ++G.body_received;
        }
    }
    if (G.out_at == usb_out_length) { gate_release_out(); G.out_at = 0; }
    if (!G.response && G.header_used == 10 && G.body_received == G.body_length) dispatch();
}
static void background(void) {
    if (!G.background) return;
    if (R.phase == READER_FAILED) {
#ifdef MG_CH559


        if (G.background == 1 && R.error == READER_BAD_CARD && G.startup_retry &&
            !G.active && !G.header_used && !usb_out_pending) {
            G.startup_retry = 0; reader_recover(&R, G.now); G.next_poll = G.now + 150;
        }
#endif
#ifdef MG_SOFT_B



        if (G.background == 2 && R.error == PN_ERR_TIMEOUT) reader_recover(&R, G.now);
#endif
        G.background = 0; notify(); return;
    }
    if (R.phase != READER_DONE) return;
#ifdef MG_CH559


    if (R.present) G.startup_retry = 1;
#endif
    if (G.background == 1 && !R.present && G.bg_tries > 1) {
        --G.bg_tries;
#ifdef MG_CH559_FELICA
        G.bg_type = G.bg_type == CARD_TYPE_A ? CARD_TYPE_B : CARD_SCAN_F;
#else
        G.bg_type = G.bg_type == CARD_TYPE_A ? CARD_TYPE_B : CARD_TYPE_A;
#endif
        reader_release(&R); reader_scan(&R, G.bg_type, 0, G.now); return;
    }
    G.background = 0; notify(); reader_release(&R); G.next_poll = G.now + 150;
}
static void service(void) {
    if (G.response || G.background) return;
    if (G.job == GATE_POWER_CLEAN) {
        if (R.phase == READER_FAILED) { fail_reply(0xfb); return; }
        if (R.phase == READER_DONE) reader_release(&R);
        if (R.phase == READER_IDLE) { reader_field_off(&R, G.now); G.job = GATE_POWER_OFF; }
    } else if (G.job == GATE_POWER_OFF) {
        if (R.phase == READER_DONE) {
            reader_release(&R); G.job = GATE_POWER_DELAY; G.next_poll = G.now + 5;
        } else if (R.phase == READER_FAILED) fail_reply(0xfb);
    } else if (G.job == GATE_POWER_DELAY) {
        if ((int16_t)(G.now - G.next_poll) >= 0) { reader_scan(&R, CARD_TYPE_A, 1, G.now); G.job = GATE_POWER_A; }
    } else if (G.job == GATE_POWER_A || G.job == GATE_POWER_B
#ifdef MG_CH559_FELICA
               || G.job == GATE_POWER_F
#endif
               ) {
        if (R.phase == READER_FAILED) fail_reply(0xfb);
        else if (R.phase == READER_DONE) {
            if (!R.present && G.job == GATE_POWER_A) {
                reader_release(&R); reader_scan(&R, CARD_TYPE_B, 1, G.now); G.job = GATE_POWER_B;
#ifdef MG_CH559_FELICA
            } else if (!R.present && G.job == GATE_POWER_B) {
                reader_release(&R); reader_scan(&R, CARD_SCAN_F, 1, G.now); G.job = GATE_POWER_F;
#endif
            } else {
                G.powered = R.active; notify();
                if (G.powered) success(BODY_ATR, R.card.atr_length);
                else { reader_release(&R); fail_reply(0xfe); }
            }
        }
    } else if (G.job == GATE_EXCHANGE) {
        if (R.phase == READER_FAILED) { notify(); fail_reply(0xfe); }
        else if (R.phase == READER_DONE) success(BODY_APDU, R.pn.payload);
    } else if (G.job == GATE_OFF_START) {
        if (R.phase == READER_FAILED) fail_reply(0xfb);
        else {
            if (R.phase == READER_DONE) reader_release(&R);
            if (R.phase == READER_IDLE) { reader_field_off(&R, G.now); G.job = GATE_OFF; }
        }
    } else if (G.job == GATE_OFF) {
        if (R.phase == READER_FAILED) fail_reply(0xfb);
        else if (R.phase == READER_DONE) { reader_release(&R); success(BODY_NONE, 0); }
    } else if (G.job == GATE_ABORT) {
        if (G.aborting && G.abort_matched &&
            (R.phase == READER_DONE || R.phase == READER_FAILED || G.abort_failed)) {
            if (R.phase == READER_DONE) reader_release(&R);
            G.aborting = G.abort_matched = G.bulk_first = 0; usb_abort_complete();
            if (R.phase == READER_FAILED || G.abort_failed) fail_reply(0xfb); else success(BODY_NONE, 0);
        }
    }
}
void gate_init(uint16_t now) {
    mg_events_clear();
#ifdef MG_UID_PROFILE
    wipe_xdata((uint8_t __xdata *)&G,sizeof(G));
#else
    uint8_t __xdata *bytes = (uint8_t __xdata *)&G;
    uint8_t i;
    for (i = 0; i < sizeof(G); ++i) bytes[i] = 0;
#endif
    G.startup_retry = 1;
    G.now = now; G.next_poll = now + 150; ccid_tx_stop(&G.tx, usb_ep2 + 64);
    reader_init(&R, now);
}
void gate_poll(uint16_t now) {
    uint8_t events = usb_events;
#ifdef MG_EVENTS
    uint8_t was_initialized = R.initialized;
#endif
    usb_events = 0; G.now = now;
    if (events & (USB_EVENT_RESET | USB_EVENT_FAULT)) {
        if (events & USB_EVENT_RESET) mg_events_publish(MG_EVENT_USB_RESET);
        if (events & USB_EVENT_FAULT) mg_events_publish(MG_EVENT_USB_FAULT);
        clean(now); G.aborting = G.abort_matched = G.abort_failed = 0;
        if (events & USB_EVENT_RESET) G.startup_retry = 1;
        if (events & USB_EVENT_FAULT) {
            G.rx_closed = 1;
#ifdef MG_CH559

            usb_accept_out = 0;
#endif
        }
        G.next_poll = now + 150;
    }
    if (events & USB_EVENT_ABORT) start_abort();
    if ((events & USB_EVENT_IN) && G.response) {
        ccid_tx_delivered(&G.tx, usb_ep2 + 64);
        if (G.tx.complete) finish_reply();
    }
    reader_poll(&R, now);
#ifdef MG_EVENTS
    if (!was_initialized && R.initialized) mg_events_publish(MG_EVENT_READER_READY);
#endif
    background();
    if (G.aborting && (int16_t)(now - G.abort_deadline) >= 0) G.abort_failed = 1;
#ifdef MG_STANDALONE_SCAN
    if (events & USB_EVENT_FAULT) return;
    if (!usb_configured) goto standalone_scan;
#else
    if (!usb_configured || (events & USB_EVENT_FAULT)) return;
#endif
    receive(); service();
    if (G.job == GATE_RECEIVE && G.header_used && G.header_used < 10 &&
        (int16_t)(now - G.deadline) >= 0) {
        G.rx_closed = 1; gate_release_out(); G.job = GATE_IDLE;
    }
    if (G.active && !G.response && G.job != GATE_REPLY &&
        (int16_t)(now - G.deadline) >= 0) {
        if (G.job == GATE_ABORT && !G.aborting) { fail_reply(0xff); }
        else {
        if (G.job == GATE_RECEIVE) {
            G.rx_closed = 1;
#ifdef MG_CH559_CLASSIC
            if (R.phase == READER_IDLE && R.pn.phase == PN_READY) wipe_xdata(R.pn.frame,PN532_FRAME_MAX);
            gate_release_out();
#endif
        }
        if (G.job != GATE_RECEIVE) { G.powered = 0; reader_recover(&R, now); notify(); }
        fail_reply(0xfe);
        }
    }
    if (G.active && !G.response && (G.command == 0x62 || G.command == 0x6f) &&
        G.job != GATE_RECEIVE && (int16_t)(now - G.next_extension) >= 0) {
        G.next_extension = now + 250; G.interim = 1; reply(1, 0, BODY_NONE, 0);
    }
#ifdef MG_STANDALONE_SCAN
standalone_scan:
#endif
    if (!G.active && !G.background && !G.aborting && !G.header_used && !usb_out_pending &&
        !G.rx_closed && (int16_t)(now - G.next_poll) >= 0) {


        if (R.phase == READER_FAILED && R.error == PN_ERR_UART && G.startup_retry) {
            G.startup_retry = 0; reader_recover(&R, now); G.next_poll = now + 150;
        }
        if (R.phase == READER_DONE) reader_release(&R);
        if (R.phase == READER_IDLE && (!usb_notification_pending()
#ifdef MG_STANDALONE_SCAN
                                     || !usb_configured
#endif
                                     )) {
            if (R.selected) {
#ifdef MG_CH559_CLASSIC



                if (R.card.classic_candidate && reader_classic_held(now)) G.next_poll=now+150;
                else
#endif
                { G.background = 2; reader_presence(&R, now); }
            }
            else {
                G.background = 1; G.bg_type = CARD_TYPE_A;
#ifdef MG_CH559_FELICA
                G.bg_tries = 3;
#else
                G.bg_tries = 2;
#endif
                reader_scan(&R, CARD_TYPE_A, 0, now);
            }
        }
    }
#ifdef MG_STANDALONE_SCAN
    if (!usb_configured) return;
#endif
    usb_accept_out = !G.rx_closed;
    send_reply(); usb_device_arm();
}
