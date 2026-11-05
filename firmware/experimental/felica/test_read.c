/* SPDX-License-Identifier: Apache-2.0 */
#include "read.h"
#include <assert.h>
#include <string.h>

int main(void) {
    FRead s;
    uint8_t idm[8]={1,2,3,4,5,6,7,8};
    uint8_t apdu[25]={0xff,0xb0,0,0,8,1,0x0b,0,2,0x80,0,0x80,1};
    uint8_t reply[142]={0};
    size_t i, n;
    assert(fr_begin(&s,idm,apdu,13)==FR_EXCHANGE);
    assert(s.command_length==19 && s.command[0]==1 && s.command[1]==18 && s.command[2]==6);
    assert(!memcmp(s.command+3,idm,8) && !memcmp(s.command+11,apdu+5,8));
    reply[0]=0;reply[1]=45;reply[2]=7;memcpy(reply+3,idm,8);reply[13]=2;
    for (i=0;i<32;++i) reply[14+i]=(uint8_t)i;
    assert(fr_complete(&s,reply,46)==FR_RESPONSE && s.response_length==35);
    assert(s.response[0]==2 && !memcmp(s.response+1,reply+14,32) && s.response[33]==0x90 && !s.response[34]);
    assert(fr_complete(&s,reply,46)==FR_INVALID);
    for (n=0;n<13;++n) assert(fr_begin(&s,idm,apdu,n)==FR_INVALID);
    apdu[5]=2;assert(fr_begin(&s,idm,apdu,13)==FR_INVALID);apdu[5]=1;
    apdu[8]=0;assert(fr_begin(&s,idm,apdu,13)==FR_INVALID);apdu[8]=2;
    apdu[9]=0x81;assert(fr_begin(&s,idm,apdu,13)==FR_INVALID);apdu[9]=0x80;
    apdu[1]=0xd6;assert(fr_begin(&s,idm,apdu,13)==FR_INVALID);apdu[1]=0xb0;
    assert(fr_begin(&s,idm,apdu,13)==FR_EXCHANGE);
    reply[3]^=1;assert(fr_complete(&s,reply,46)==FR_INVALID);reply[3]^=1;
    assert(fr_begin(&s,idm,apdu,13)==FR_EXCHANGE);
    reply[1]=12;reply[11]=1;assert(fr_complete(&s,reply,13)==FR_RESPONSE);
    assert(s.response_length==2 && s.response[0]==0x63 && !s.response[1]);
    fr_clear(&s);for (i=0;i<sizeof s;++i) assert(!((uint8_t *)&s)[i]);
    return 0;
}
