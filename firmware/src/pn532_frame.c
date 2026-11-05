/* SPDX-License-Identifier: Apache-2.0 */
/* C adaptation of ManeKey manekey-pn532/src/lib.rs, 2026-10-25.
 * No external Rust dependencies; strict UART frame boundary instead of padding. */
#include "pn532_frame.h"

uint8_t pn532_frame_length(const uint8_t __xdata *MG_LOCAL frame, uint16_t MG_LOCAL available,
    uint16_t __xdata *MG_LOCAL total) MG_CALL {
    uint16_t MG_LOCAL packet;
    if (available < 5) return PN_TRUNCATED;
    if (frame[0] || frame[1] || frame[2] != 0xff) return PN_HEADER;
    if ((!frame[3] && frame[4] == 0xff) || (frame[3] == 0xff && !frame[4])) {
        *total = 6; return PN_OK;
    }
    if (frame[3] == 0xff && frame[4] == 0xff) {
        if (available < 8) return PN_TRUNCATED;
        if ((uint8_t)(frame[5] + frame[6] + frame[7])) return PN_LENGTH_CHECKSUM;
        packet = ((uint16_t)frame[5] << 8) | frame[6];
        if (packet > PN532_PACKET_MAX) return PN_TOO_LONG;
        if (!packet) return PN_HEADER;
        *total = packet + 10;
    } else {
        if (!frame[3] || (uint8_t)(frame[3] + frame[4])) return PN_LENGTH_CHECKSUM;
        *total = (uint16_t)frame[3] + 7;
    }
    return PN_OK;
}

uint8_t pn532_encode(uint8_t MG_LOCAL command, const uint8_t __xdata *MG_LOCAL data,
    uint16_t MG_LOCAL length, uint8_t __xdata *MG_LOCAL out, uint16_t MG_LOCAL capacity,
    uint16_t __xdata *MG_LOCAL total) MG_CALL {
    uint16_t MG_LOCAL packet, i, size;
    uint8_t MG_LOCAL head, sum;
    if (length > PN532_PACKET_MAX - 2) return PN_TOO_LONG;
    packet = length + 2;
    head = packet > 255 ? 8 : 5;
    size = head + packet + 2;
    if (capacity < size) return PN_CAPACITY;
    out[0] = out[1] = 0; out[2] = 0xff;
    if (head == 8) {
        out[3] = out[4] = 0xff; out[5] = packet >> 8; out[6] = packet;
#ifdef MG_COMPACT_ABI
        out[7] = (uint8_t)(0 - (packet >> 8) - (uint8_t)packet);
#else
        out[7] = (uint8_t)(0 - out[5] - out[6]);
#endif
    } else {
        out[3] = packet; out[4] = (uint8_t)(0 - packet);
    }
    out[head] = 0xd4; out[head + 1] = command;
    sum = (uint8_t)(0xd4 + command);
    for (i = 0; i < length; ++i) {
#ifdef MG_COMPACT_ABI
        sum += (out[head + 2 + i] = data[i]);
#else
        out[head + 2 + i] = data[i]; sum += data[i];
#endif
    }
    out[size - 2] = (uint8_t)(0 - sum); out[size - 1] = 0;
    *total = size;
    return PN_OK;
}

uint8_t pn532_decode(uint8_t MG_LOCAL command, const uint8_t __xdata *MG_LOCAL frame,
    uint16_t MG_LOCAL length, uint16_t __xdata *MG_LOCAL offset, uint16_t __xdata *MG_LOCAL payload) MG_CALL {
    uint16_t MG_LOCAL total, end, i;
    uint8_t MG_LOCAL error, head, sum = 0;


    error = pn532_frame_length(frame, length, offset);
    if (error) return error;
    total = *offset;
    if (length < total) return PN_TRUNCATED;
    if (length > total) return PN_TRAILING;
    if (total == 6) return PN_HEADER;
    head = frame[3] == 0xff && frame[4] == 0xff ? 8 : 5;
    end = total - 2;
    for (i = head; i <= end; ++i) sum += frame[i];
    if (sum) return PN_DATA_CHECKSUM;
    if (frame[end + 1]) return PN_POSTAMBLE;
    if (end - head == 1 && frame[head] == 0x7f) return PN_SYNTAX;
    if (end - head < 2) return PN_HEADER;
    if (frame[head] != 0xd5) return PN_DIRECTION;
    if (frame[head + 1] != (uint8_t)(command + 1)) return PN_COMMAND;
    *offset = head + 2; *payload = end - head - 2;
    return PN_OK;
}
