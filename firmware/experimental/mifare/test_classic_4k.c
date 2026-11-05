/* SPDX-License-Identifier: Apache-2.0 */

#include "classic.h"
#include <assert.h>
#include <string.h>
int main(void) {
    McSession s; uint8_t uid[4]={1,2,3,4}, out[32], ok[1]={0}; size_t n;
    uint8_t key[11]={0xff,0x82,0,0,6,1,2,3,4,5,6};
    uint8_t auth[10]={0xff,0x86,0,0,5,1,0,0,0x60,0};
    uint8_t read[5]={0xff,0xb0,0,0,16};
    uint8_t write[21]={0xff,0xd6,0,0,16};
    assert(mc_attach_4k(&s,uid,4));
    assert(mc_command(&s,key,sizeof(key),out,sizeof(out),&n)==MC_RESPONSE);
    for (unsigned b=0;b<256;b++) {
        auth[7]=b;
        assert(mc_command(&s,auth,sizeof(auth),out,sizeof(out),&n)==MC_EXCHANGE);
        assert(mc_complete(&s,ok,1,out,sizeof(out),&n)==MC_RESPONSE);
        write[3]=b;
        int trailer = b < 128 ? b%4==3 : b%16==15;
        int result=mc_command(&s,write,sizeof(write),out,sizeof(out),&n);
        if (!b || trailer) assert(result==MC_RESPONSE && n==2 && out[0]==0x69 && out[1]==0x86);
        else { assert(result==MC_EXCHANGE && out[2]==b); assert(mc_complete(&s,ok,1,out,sizeof(out),&n)==MC_RESPONSE); }
        if (b==127 || b==143 || b==254) {
            read[3]=b+1;
            result=mc_command(&s,read,sizeof(read),out,sizeof(out),&n);
            if (b!=254) assert(result==MC_RESPONSE && out[0]==0x69 && out[1]==0x82);
            else assert(result==MC_EXCHANGE && out[2]==255);
            if (result==MC_EXCHANGE) { uint8_t data[17]={0}; assert(mc_complete(&s,data,17,out,sizeof(out),&n)==MC_RESPONSE); }
        }
    }
    assert(mc_attach(&s,uid,4));auth[7]=64;
    assert(mc_command(&s,auth,sizeof(auth),out,sizeof(out),&n)==MC_RESPONSE && out[0]==0x6a);
    mc_clear(&s); return 0;
}
