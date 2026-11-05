/* SPDX-License-Identifier: Apache-2.0 */
#include "poll.h"
#include <assert.h>
#include <string.h>

int main(void) {
    FPoll s;
    uint8_t reply[22] = {1,1,18,1,1,2,3,4,5,6,7,8};
    uint8_t apdu[5] = {0xff,0xca,0,0,0}, out[10];
    const uint8_t poll[] = {1,1,0,0xff,0xff,0,0};
    size_t n, i;
    assert(fp_poll_request(out, 6) == FP_INVALID);
    assert(fp_poll_request(out, sizeof out) == 7 && memcmp(out, poll, 7) == 0);
    assert(fp_parse(&s, reply, 20) == FP_FOUND);
    assert(fp_get_data(&s, apdu, 5, out, sizeof out, &n) == FP_FOUND);
    assert(n == 10 && memcmp(out, reply+4, 8) == 0 && out[8] == 0x90 && !out[9]);
    assert(fp_get_data(&s, apdu, 5, out, 9, &n) == FP_INVALID && n == 0);
    apdu[2] = 1;
    assert(fp_get_data(&s, apdu, 5, out, sizeof out, &n) == FP_INVALID && n == 0);
    reply[2] = 20;
    assert(fp_parse(&s, reply, 22) == FP_FOUND);
    for (i = 0; i < 22; ++i) {
        if (i == 20) continue;
        assert(fp_parse(&s, reply, i) == FP_INVALID);
        assert(!s.present);
    }
    reply[2] = 18; reply[3] = 2;
    assert(fp_parse(&s, reply, 20) == FP_INVALID && !s.present);
    reply[0] = 0;
    assert(fp_parse(&s, reply, 1) == FP_NONE && !s.present);
    for (i = 0; i < sizeof s.idm; ++i) assert(!s.idm[i]);
    return 0;
}
