/* SPDX-License-Identifier: Apache-2.0 */

#include "isodep_b.h"
#ifdef MG_SINGLETON
__xdata IsoDepB depb_state;
#define B(s) (&depb_state)
#ifdef MG_COMPACT_ABI
#define VALID(s) 1
#else
#define VALID(s) ((s)==&depb_state)
#endif
#else
#define B(s) (s)
#define VALID(s) 1
#endif

static const __code uint8_t frame_sizes[8] = {16,24,32,40,48,64,96,128};

void MG_ENTRY(depb_clear)(MG_SELF_ONLY(IsoDepB, s)) MG_CALL {
#ifndef MG_UID_PROFILE
    uint16_t i;
#endif
    if (!VALID(s)) return;
#ifdef MG_UID_PROFILE
    wipe_xdata((uint8_t __xdata *)B(s),sizeof(*B(s)));
#else
    for (i=0;i<sizeof(*B(s));++i) ((uint8_t __xdata *)B(s))[i]=0;
#endif
}
static uint8_t reject(IsoDepB __xdata *s) MG_CALL {
    (void)s;
    depb_clear(B(s));B(s)->phase=DEPB_FAILED;return 1;
}
uint8_t MG_ENTRY(depb_begin)(MG_SELF_PARAM(IsoDepB, s) const uint8_t __xdata *request,
                  uint16_t length,uint8_t fsci,uint8_t cid) MG_CALL {
#ifndef MG_UID_PROFILE
    uint16_t i;
#endif
    if (!VALID(s)) return 1;
    if (B(s)->phase!=DEPB_CLOSED || length<4 || length>261 || fsci>8 || cid>14)
        return reject(B(s));
    B(s)->length=length;B(s)->cid=cid;B(s)->header=cid?2:1;
    B(s)->limit=fsci==8?254-B(s)->header:frame_sizes[fsci]-B(s)->header-2;
#ifdef MG_UID_PROFILE
    copy_xdata(B(s)->buffer,request,length);
#else
    for (i=0;i<length;++i) B(s)->buffer[i]=request[i];
#endif
    B(s)->phase=DEPB_SEND_I;B(s)->wtx_left=16;
    return 0;
}
uint16_t MG_ENTRY(depb_next)(MG_SELF_PARAM(IsoDepB, s) uint8_t __xdata *out) MG_CALL {
#ifdef MG_UID_PROFILE
    uint16_t count;
#else
    uint16_t count,i;
#endif
    if (!VALID(s)) return 0;
    if (B(s)->header==2) out[1]=B(s)->cid;
    if (B(s)->phase==DEPB_SEND_WTX) {
        out[0]=B(s)->header==2?0xfa:0xf2;out[B(s)->header]=B(s)->wtx;B(s)->phase=B(s)->resume;return B(s)->header+1;
    }
    if (B(s)->phase==DEPB_SEND_ACK) {
        out[0]=(B(s)->header==2?0xaa:0xa2)|B(s)->block;B(s)->phase=DEPB_WAIT_I;return B(s)->header;
    }
    if (B(s)->phase!=DEPB_SEND_I) { reject(B(s));return 0; }
    count=B(s)->length-B(s)->offset;
    if (count>B(s)->limit) count=B(s)->limit;
#ifdef MG_UID_PROFILE
    copy_xdata(out+B(s)->header,B(s)->buffer+B(s)->offset,count);
#else
    for (i=0;i<count;++i) out[B(s)->header+i]=B(s)->buffer[B(s)->offset+i];
#endif
    B(s)->offset+=count;
    out[0]=(B(s)->header==2?0x0a:0x02)|B(s)->block;
    if (B(s)->offset<B(s)->length) { out[0]|=0x10;B(s)->phase=DEPB_WAIT_ACK; }
    else { B(s)->phase=DEPB_WAIT_I;B(s)->used=0; }
    return count+B(s)->header;
}
uint8_t MG_ENTRY(depb_receive)(MG_SELF_PARAM(IsoDepB, s) const uint8_t __xdata *data,
                     uint16_t length) MG_CALL {
#ifdef MG_UID_PROFILE
    uint16_t count;
#else
    uint16_t i,count;
#endif
    uint8_t pcb;
    if (!VALID(s)) return 1;

    if ((B(s)->phase!=DEPB_WAIT_ACK && B(s)->phase!=DEPB_WAIT_I) || length<B(s)->header || length>62 ||
        (B(s)->header==2 && data[1]!=B(s)->cid))
        return reject(B(s));
    pcb=data[0];
    if (pcb==(B(s)->header==2?0xfa:0xf2)) {
        if (length!=B(s)->header+1 || !data[B(s)->header] || data[B(s)->header]>59 || !B(s)->wtx_left) return reject(B(s));
        --B(s)->wtx_left;B(s)->wtx=data[B(s)->header];B(s)->resume=B(s)->phase;B(s)->phase=DEPB_SEND_WTX;return 0;
    }
    if (B(s)->phase==DEPB_WAIT_ACK) {
        if (length!=B(s)->header || pcb!=(uint8_t)((B(s)->header==2?0xaa:0xa2)|B(s)->block)) return reject(B(s));
        B(s)->block^=1;B(s)->phase=DEPB_SEND_I;return 0;
    }


    if (length<=B(s)->header || (pcb&0xef)!=(uint8_t)((B(s)->header==2?0x0a:0x02)|B(s)->block)) return reject(B(s));
    count=length-B(s)->header;
    if (count>258-B(s)->used) return reject(B(s));
#ifdef MG_UID_PROFILE
    copy_xdata(B(s)->buffer+B(s)->used,data+B(s)->header,count);
#else
    for (i=0;i<count;++i) B(s)->buffer[B(s)->used+i]=data[B(s)->header+i];
#endif
    B(s)->used+=count;B(s)->block^=1;
    if (pcb&0x10) B(s)->phase=DEPB_SEND_ACK;
    else {
        if (B(s)->used<2) return reject(B(s));
        B(s)->phase=DEPB_DONE;
    }
    return 0;
}
