/* SPDX-License-Identifier: AGPL-3.0-only */
#include "classic.h"
#include <assert.h>
#include <string.h>

int main(void) {
    McSession s; size_t len; uint8_t out[32], ok[] = {0}, bad[] = {1};
    uint8_t uid[] = {1,2,3,4}, key[] = {0xff,0x82,0,0,6,1,2,3,4,5,6};
    uint8_t auth[] = {0xff,0x86,0,0,5,1,0,4,0x60,0};
    uint8_t read[] = {0xff,0xb0,0,4,16};
    uint8_t write[] = {0xff,0xd6,0,4,16,0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15};
    uint8_t payload[17] = {0}; int i;
    assert(mc_attach(&s, uid, 4));
    assert(mc_command(&s,read,sizeof read,out,sizeof out,&len)==MC_RESPONSE && out[0]==0x69);
    assert(mc_command(&s,auth,sizeof auth,out,sizeof out,&len)==MC_RESPONSE && out[0]==0x69);
    assert(mc_command(&s,key,sizeof key,out,sizeof out,&len)==MC_RESPONSE && out[0]==0x90);
    assert(mc_command(&s,auth,sizeof auth,out,sizeof out,&len)==MC_EXCHANGE && len==13);
    assert(out[0]==1 && out[1]==0x60 && out[2]==4 && !memcmp(out+3,key+5,6) && !memcmp(out+9,uid,4));
    assert(mc_command(&s,read,sizeof read,out,sizeof out,&len)==MC_REJECT);
    assert(mc_complete(&s,ok,sizeof ok,out,sizeof out,&len)==MC_RESPONSE && out[0]==0x90);
    assert(mc_command(&s,read,sizeof read,out,sizeof out,&len)==MC_EXCHANGE && len==3 && out[1]==0x30);
    for (i=0;i<16;i++) payload[i+1]=(uint8_t)i;
    assert(mc_complete(&s,payload,sizeof payload,out,sizeof out,&len)==MC_RESPONSE && len==18 && !memcmp(out,payload+1,16));
    assert(mc_command(&s,write,sizeof write,out,sizeof out,&len)==MC_EXCHANGE && len==19 && out[1]==0xa0);
    assert(mc_complete(&s,ok,sizeof ok,out,sizeof out,&len)==MC_RESPONSE && out[0]==0x90);
    write[3]=7; assert(mc_command(&s,write,sizeof write,out,sizeof out,&len)==MC_RESPONSE && out[0]==0x69 && out[1]==0x86);
    write[3]=0; assert(mc_command(&s,write,sizeof write,out,sizeof out,&len)==MC_RESPONSE && out[0]==0x69 && out[1]==0x86);
    read[3]=8; assert(mc_command(&s,read,sizeof read,out,sizeof out,&len)==MC_RESPONSE && out[0]==0x69 && out[1]==0x82);
    read[3]=4; assert(mc_command(&s,read,sizeof read,out,sizeof out,&len)==MC_EXCHANGE);
    assert(mc_complete(&s,bad,sizeof bad,out,sizeof out,&len)==MC_RESPONSE && out[0]==0x63);
    assert(mc_command(&s,read,sizeof read,out,sizeof out,&len)==MC_RESPONSE && out[0]==0x69);
    auth[8]=0x61; assert(mc_command(&s,auth,sizeof auth,out,sizeof out,&len)==MC_EXCHANGE && out[1]==0x61);
    assert(mc_complete(&s,ok,sizeof ok,out,sizeof out,&len)==MC_RESPONSE);
    assert(mc_command(&s,read,sizeof read,out,sizeof out,&len)==MC_EXCHANGE);
    assert(mc_complete(&s,payload,16,out,sizeof out,&len)==MC_RESPONSE && !s.authenticated);

    for (i=0;i<64;i++) {
        int result; assert(mc_attach(&s,uid,4));
        assert(mc_command(&s,key,sizeof key,out,sizeof out,&len)==MC_RESPONSE);
        assert(mc_command(&s,auth,sizeof auth,out,sizeof out,&len)==MC_EXCHANGE);
        assert(mc_complete(&s,ok,sizeof ok,out,sizeof out,&len)==MC_RESPONSE);
        write[3]=(uint8_t)i;
        result=mc_command(&s,write,sizeof write,out,sizeof out,&len);
        if (i>=4 && i<=6) {
            assert(result==MC_EXCHANGE && out[2]==i);
            assert(mc_complete(&s,ok,sizeof ok,out,sizeof out,&len)==MC_RESPONSE);
        } else {
            assert(result==MC_RESPONSE && out[0]==0x69);
        }
    }
    write[3]=64;
    assert(mc_command(&s,write,sizeof write,out,sizeof out,&len)==MC_RESPONSE && out[0]==0x6a);
    auth[5]=2;
    assert(mc_command(&s,auth,sizeof auth,out,sizeof out,&len)==MC_RESPONSE && out[0]==0x6a);
    mc_clear(&s); for (i=0;i<(int)sizeof s;i++) assert(((unsigned char *)&s)[i]==0);
    assert(!mc_attach(&s,uid,3));
    assert(mc_command(&s,read,sizeof read,out,sizeof out,&len)==MC_REJECT);
    return 0;
}
