/* SPDX-License-Identifier: Apache-2.0 */
/* C adaptation of ManeKey manekey-pn532/src/lib.rs, 2026-10-25. */
#ifndef PAKURI_PN532_FRAME_H
#define PAKURI_PN532_FRAME_H
#include "memory.h"
#define PN532_PACKET_MAX 265
#define PN532_FRAME_MAX 275
enum {
    PN_OK, PN_TRUNCATED, PN_HEADER, PN_LENGTH_CHECKSUM, PN_TOO_LONG,
    PN_CAPACITY, PN_DATA_CHECKSUM, PN_POSTAMBLE, PN_DIRECTION,
    PN_COMMAND, PN_SYNTAX, PN_TRAILING
};


uint8_t pn532_frame_length(const uint8_t __xdata *MG_LOCAL frame, uint16_t MG_LOCAL available,
    uint16_t __xdata *MG_LOCAL total) MG_CALL;


uint8_t pn532_encode(uint8_t MG_LOCAL command, const uint8_t __xdata *MG_LOCAL data,
    uint16_t MG_LOCAL length, uint8_t __xdata *MG_LOCAL out, uint16_t MG_LOCAL capacity,
    uint16_t __xdata *MG_LOCAL total) MG_CALL;


uint8_t pn532_decode(uint8_t MG_LOCAL command, const uint8_t __xdata *MG_LOCAL frame,
    uint16_t MG_LOCAL length, uint16_t __xdata *MG_LOCAL offset, uint16_t __xdata *MG_LOCAL payload) MG_CALL;
#endif
