/* SPDX-License-Identifier: AGPL-3.0-only */
#include "read.h"

void fr_clear(FRead FR_XDATA *s) {
    size_t i;
    volatile uint8_t FR_XDATA *p=(volatile uint8_t FR_XDATA *)s;
    if (!s) return;
    for (i=0;i<sizeof(*s);++i) p[i]=0;
}

int fr_begin(FRead FR_XDATA *s, const uint8_t FR_XDATA *idm,
             const uint8_t FR_XDATA *a, size_t n) {
    size_t i, lc, blocks;
    if (!s) return FR_INVALID;
    fr_clear(s);
    if (!idm || !a || n<11 || a[0]!=0xff || a[1]!=0xb0 || a[2] || a[3]) return FR_INVALID;
    lc=a[4];
    if (lc<6 || lc>20 || (n!=5+lc && !(n==6+lc && a[n-1]==0))) return FR_INVALID;
    if (a[5]!=1) return FR_INVALID;
    blocks=a[8];
    if (!blocks || blocks>8 || lc!=4+blocks*2) return FR_INVALID;
    for (i=0;i<blocks;++i) if (a[9+2*i]!=0x80) return FR_INVALID;
    for (i=0;i<8;++i) { s->idm[i]=idm[i];s->command[3+i]=idm[i]; }
    s->command[0]=1;
    s->command[1]=(uint8_t)(10+lc);
    s->command[2]=6;
    for (i=0;i<lc;++i) s->command[11+i]=a[5+i];
    s->command_length=(uint8_t)(11+lc);s->blocks=(uint8_t)blocks;s->pending=1;
    return FR_EXCHANGE;
}

int fr_complete(FRead FR_XDATA *s, const uint8_t FR_XDATA *r, size_t n) {
    size_t i, count;
    if (!s || !s->pending || !r) { if (s) fr_clear(s); return FR_INVALID; }
    s->pending=0;
    if (n<13 || r[0] || r[1]!=n-1 || r[2]!=7) { fr_clear(s);return FR_INVALID; }
    for (i=0;i<8;++i) if (r[3+i]!=s->idm[i]) { fr_clear(s);return FR_INVALID; }
    if (r[11] || r[12]) {
        if (n!=13) { fr_clear(s);return FR_INVALID; }
        s->response[0]=0x63;s->response[1]=0;s->response_length=2;return FR_RESPONSE;
    }
    count=s->blocks;
    if (n!=14+count*16 || r[13]!=count) { fr_clear(s);return FR_INVALID; }
    s->response[0]=(uint8_t)count;
    for (i=0;i<count*16;++i) s->response[1+i]=r[14+i];
    s->response[1+count*16]=0x90;s->response[2+count*16]=0;
    s->response_length=(uint8_t)(3+count*16);
    return FR_RESPONSE;
}
