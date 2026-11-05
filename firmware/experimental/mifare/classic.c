/* SPDX-License-Identifier: AGPL-3.0-only */
#include "classic.h"

enum { P_AUTH = 1, P_READ = 2, P_WRITE = 3 };
static void wipe(void MC_XDATA *p, size_t n) { volatile uint8_t MC_XDATA *q = p; while (n--) *q++ = 0; }
static int sw(uint8_t MC_XDATA *out, size_t cap, size_t MC_XDATA *n, uint8_t a, uint8_t b) {
    if (!out || !n || cap < 2) return MC_REJECT;
    out[0] = a; out[1] = b; *n = 2; return MC_RESPONSE;
}
void mc_clear(McSession MC_XDATA *s) { if (s) wipe(s, sizeof(*s)); }
int mc_attach(McSession MC_XDATA *s, const uint8_t MC_XDATA *uid, size_t n) {
    size_t i;
    if (!s) return 0;
    mc_clear(s);
    if (!uid || (n != 4
#ifdef MG_CLASSIC_7B
                 && n != 7
#endif
                )) return 0;
#ifdef MG_CLASSIC_7B

    for (i = 0; i < 4; ++i) s->uid[i] = uid[n-4+i];
#else
    for (i = 0; i < 4; ++i) s->uid[i] = uid[i];
#endif
    s->present = 1; return 1;
}
#ifdef MG_CLASSIC_4K
int mc_attach_4k(McSession MC_XDATA *s, const uint8_t MC_XDATA *uid, size_t n) {
    if (!mc_attach(s, uid, n)) return 0;
    s->capacity_4k = 1; return 1;
}
static uint8_t sector_of(uint8_t block) {
    return block < 128 ? block / 4 : 32 + (block - 128) / 16;
}
static uint8_t trailer(uint8_t block) {
    return block < 128 ? (block % 4 == 3) : (block % 16 == 15);
}
#else
#define sector_of(block) ((block) / 4)
#define trailer(block) ((block) % 4 == 3)
#endif
int mc_command(McSession MC_XDATA *s, const uint8_t MC_XDATA *a, size_t n,
               uint8_t MC_XDATA *out, size_t cap, size_t MC_XDATA *out_len) {
    size_t i; uint8_t block;
    if (!s || !a || !out || !out_len) return MC_REJECT;
    *out_len = 0;
    if (!s->present || s->pending) return MC_REJECT;
    if (n < 5 || a[0] != 0xff) return sw(out, cap, out_len, 0x6e, 0);
    if (a[1] == 0x82) {
        if (n != 11 || a[2] || a[3] || a[4] != 6) return sw(out, cap, out_len, 0x6a, 0x80);
        if (cap < 2) return MC_REJECT;
        wipe(s->key, sizeof(s->key));
        for (i = 0; i < 6; ++i) s->key[i] = a[5+i];
        s->key_loaded = 1; s->authenticated = 0;
        return sw(out, cap, out_len, 0x90, 0);
    }
    if (a[1] == 0x86) {
        if (n != 10 || a[2] || a[3] || a[4] != 5 || a[5] != 1 || a[6] ||
            (a[7] > 63
#ifdef MG_CLASSIC_4K
             && !s->capacity_4k
#endif
            ) || (a[8] != 0x60 && a[8] != 0x61) || a[9])
            return sw(out, cap, out_len, 0x6a, 0x80);
        if (!s->key_loaded) return sw(out, cap, out_len, 0x69, 0x82);
        if (cap < 13) return MC_REJECT;
        s->authenticated = 0; s->sector = sector_of(a[7]); s->pending = P_AUTH;
        out[0]=1; out[1]=a[8]; out[2]=a[7];
        for (i=0;i<6;++i) out[3+i]=s->key[i];
        for (i=0;i<4;++i) out[9+i]=s->uid[i];
        *out_len=13; return MC_EXCHANGE;
    }
    if (a[1] == 0xb0 || a[1] == 0xd6) {
        if (a[2] || (a[3] > 63
#ifdef MG_CLASSIC_4K
                     && !s->capacity_4k
#endif
                    )) return sw(out, cap, out_len, 0x6a, 0x82);
        block = a[3];
        if ((a[1] == 0xb0 && (n != 5 || a[4] != 16)) ||
            (a[1] == 0xd6 && (n != 21 || a[4] != 16)))
            return sw(out, cap, out_len, 0x67, 0);

        if (a[1] == 0xd6 && (!block || trailer(block)))
            return sw(out, cap, out_len, 0x69, 0x86);
        if (!s->authenticated || s->sector != sector_of(block))
            return sw(out, cap, out_len, 0x69, 0x82);
        if (cap < (a[1] == 0xb0 ? 3u : 19u)) return MC_REJECT;
        out[0]=1; out[1]=a[1] == 0xb0 ? 0x30 : 0xa0; out[2]=block;
        if (a[1] == 0xd6) for (i=0;i<16;++i) out[3+i]=a[5+i];
        *out_len = a[1] == 0xb0 ? 3 : 19;
        s->pending = a[1] == 0xb0 ? P_READ : P_WRITE;
        return MC_EXCHANGE;
    }
    return sw(out, cap, out_len, 0x6d, 0);
}
int mc_complete(McSession MC_XDATA *s, const uint8_t MC_XDATA *reply, size_t n,
                uint8_t MC_XDATA *out, size_t cap, size_t MC_XDATA *out_len) {
    uint8_t pending; size_t i;
    if (!s || !out || !out_len || !s->present || !s->pending) return MC_REJECT;
    *out_len = 0; pending = s->pending; s->pending = 0;
    if (!reply || n != (pending == P_READ ? 17u : 1u) || reply[0]) {
        s->authenticated = 0;
        return sw(out, cap, out_len, 0x63, 0);
    }
    if (pending == P_READ) {
        if (cap < 18) { s->authenticated = 0; return MC_REJECT; }
        for (i=0;i<16;++i) out[i]=reply[i+1];
        out[16]=0x90; out[17]=0; *out_len=18; return MC_RESPONSE;
    }
    if (cap < 2) { s->authenticated = 0; return MC_REJECT; }
    if (pending == P_AUTH) s->authenticated = 1;
    return sw(out, cap, out_len, 0x90, 0);
}
