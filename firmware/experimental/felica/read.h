/* SPDX-License-Identifier: AGPL-3.0-only */
#ifndef MG_FELICA_READ_H
#define MG_FELICA_READ_H
#include <stddef.h>
#include <stdint.h>
#if defined(__SDCC) && defined(MG_CH559_FELICA)
#define FR_XDATA __xdata
#define FR_CALL __reentrant
#else
#define FR_XDATA
#define FR_CALL
#endif


typedef struct {
    uint8_t idm[8], command[31], response[131];
    uint8_t command_length, response_length, blocks, pending;
} FRead;
enum { FR_RESPONSE=0, FR_EXCHANGE=1, FR_INVALID=2 };
void fr_clear(FRead FR_XDATA *s) FR_CALL;
int fr_begin(FRead FR_XDATA *s, const uint8_t FR_XDATA *idm,
             const uint8_t FR_XDATA *apdu, size_t n) FR_CALL;
int fr_complete(FRead FR_XDATA *s, const uint8_t FR_XDATA *reply, size_t n) FR_CALL;
#endif
