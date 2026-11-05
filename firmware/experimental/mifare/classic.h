/* SPDX-License-Identifier: AGPL-3.0-only */
#ifndef MG_CLASSIC_H
#define MG_CLASSIC_H
#include <stdint.h>
#include <stddef.h>

#if defined(__SDCC) && defined(MG_CLASSIC_STACK_AUTO)
#define MC_CALL __reentrant
#define MC_XDATA __xdata
#else
#define MC_CALL
#define MC_XDATA
#endif


enum { MC_RESPONSE = 0, MC_EXCHANGE = 1, MC_REJECT = 2 };
typedef struct {
    uint8_t key[6], uid[4];
    uint8_t key_loaded, present, pending, authenticated, sector;
#ifdef MG_CLASSIC_4K
    uint8_t capacity_4k;
#endif
} McSession;

void mc_clear(McSession MC_XDATA *s) MC_CALL;
int mc_attach(McSession MC_XDATA *s, const uint8_t MC_XDATA *uid, size_t uid_len) MC_CALL;
#ifdef MG_CLASSIC_4K
int mc_attach_4k(McSession MC_XDATA *s, const uint8_t MC_XDATA *uid, size_t uid_len) MC_CALL;
#endif

int mc_command(McSession MC_XDATA *s, const uint8_t MC_XDATA *apdu, size_t n,
               uint8_t MC_XDATA *out, size_t capacity, size_t MC_XDATA *out_len) MC_CALL;
int mc_complete(McSession MC_XDATA *s, const uint8_t MC_XDATA *pn_reply, size_t n,
                uint8_t MC_XDATA *out, size_t capacity, size_t MC_XDATA *out_len) MC_CALL;
#endif
