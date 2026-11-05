/* SPDX-License-Identifier: Apache-2.0 */
#ifndef PAKURI_ISODEP_B_H
#define PAKURI_ISODEP_B_H
#include "memory.h"
enum { DEPB_CLOSED, DEPB_SEND_I, DEPB_WAIT_ACK, DEPB_WAIT_I,
       DEPB_SEND_ACK, DEPB_SEND_WTX, DEPB_DONE, DEPB_FAILED };
typedef struct {

    uint8_t buffer[261];
    uint16_t length, offset, used;
    uint8_t limit, block, cid, header, phase, resume, wtx, wtx_left;
} IsoDepB;
#ifdef MG_SINGLETON
extern __xdata IsoDepB depb_state;
#endif
void MG_ENTRY(depb_clear)(MG_SELF_ONLY(IsoDepB, s)) MG_CALL;


uint8_t MG_ENTRY(depb_begin)(MG_SELF_PARAM(IsoDepB, s) const uint8_t __xdata *request,
                  uint16_t length, uint8_t fsci, uint8_t cid) MG_CALL;

uint16_t MG_ENTRY(depb_next)(MG_SELF_PARAM(IsoDepB, s) uint8_t __xdata *out) MG_CALL;

uint8_t MG_ENTRY(depb_receive)(MG_SELF_PARAM(IsoDepB, s) const uint8_t __xdata *data,
                     uint16_t length) MG_CALL;
#ifdef MG_COMPACT_ABI
#define depb_clear(s) \
    ((s)==(&depb_state) ? MG_ENTRY(depb_clear)() : (void)0)
#define depb_begin(s,request,length,fsci,cid) \
    ((s)==(&depb_state) ? MG_ENTRY(depb_begin)((request),(length),(fsci),(cid)) : 1)
#define depb_next(s,out) \
    ((s)==(&depb_state) ? MG_ENTRY(depb_next)((out)) : 0)
#define depb_receive(s,data,length) \
    ((s)==(&depb_state) ? MG_ENTRY(depb_receive)((data),(length)) : 1)
#endif
#endif
