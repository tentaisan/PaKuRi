/* SPDX-License-Identifier: Apache-2.0 */

#include "../src/reader.h"
#include "../src/isodep_b.h"
#ifdef MG_CCID_TX_ONLY
#include "../src/gate.h"
#endif
#ifndef MG_ABI_BLOCK_ONLY
void (reader_init)(Reader __xdata *r, uint16_t now) { reader_init(r,now); }
void (reader_recover)(Reader __xdata *r, uint16_t now) { reader_recover(r,now); }
void (reader_poll)(Reader __xdata *r, uint16_t now) { reader_poll(r,now); }
void (reader_release)(Reader __xdata *r) { reader_release(r); }
uint8_t (reader_scan)(Reader __xdata *r, uint8_t type, uint8_t activate, uint16_t now) { return reader_scan(r,type,activate,now); }
uint8_t (reader_presence)(Reader __xdata *r, uint16_t now) { return reader_presence(r,now); }
uint8_t (reader_field_off)(Reader __xdata *r, uint16_t now) { return reader_field_off(r,now); }
uint8_t (reader_exchange)(Reader __xdata *r, const uint8_t __xdata *data,
    uint16_t length, uint16_t now) { return reader_exchange(r,data,length,now); }
#endif
void (depb_clear)(IsoDepB __xdata *s) { depb_clear(s); }
uint8_t (depb_begin)(IsoDepB __xdata *s, const uint8_t __xdata *request,
                  uint16_t length, uint8_t fsci, uint8_t cid) { return depb_begin(s,request,length,fsci,cid); }
uint16_t (depb_next)(IsoDepB __xdata *s, uint8_t __xdata *out) { return depb_next(s,out); }
uint8_t (depb_receive)(IsoDepB __xdata *s, const uint8_t __xdata *data,
                     uint16_t length) { return depb_receive(s,data,length); }
#ifndef MG_ABI_BLOCK_ONLY
void (pn_transport_init)(PnTransport __xdata *s) { pn_transport_init(s); }
uint8_t (pn_transport_begin)(PnTransport __xdata *s, uint8_t command,
    const uint8_t __xdata *data, uint16_t length, uint16_t response_bound,
    uint16_t now, uint16_t timeout) { return pn_transport_begin(s,command,data,length,response_bound,now,timeout); }
void (pn_transport_poll)(PnTransport __xdata *s, uint16_t now) { pn_transport_poll(s,now); }
void (pn_transport_recover)(PnTransport __xdata *s, uint16_t now) { pn_transport_recover(s,now); }
void (pn_transport_release)(PnTransport __xdata *s) { pn_transport_release(s); }
#ifdef MG_CCID_TX_ONLY
uint8_t (ccid_tx_init)(CcidTx __xdata *s, uint16_t total,
    uint8_t __xdata *packet) { return ccid_tx_init(s,total,packet); }
uint8_t (ccid_tx_push)(CcidTx __xdata *s, const uint8_t __xdata *data,
    uint8_t length, uint8_t __xdata *packet) { return ccid_tx_push(s,data,length,packet); }
uint8_t (ccid_tx_delivered)(CcidTx __xdata *s, uint8_t __xdata *packet) { return ccid_tx_delivered(s,packet); }
void (ccid_tx_stop)(CcidTx __xdata *s, uint8_t __xdata *packet) { ccid_tx_stop(s,packet); }
#endif

#endif
