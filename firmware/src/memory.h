/* SPDX-License-Identifier: Apache-2.0 */
#ifndef PAKURI_MEMORY_H
#define PAKURI_MEMORY_H
#include <stdint.h>
#ifndef __SDCC
#define __xdata
#define __idata
#define __data
#define __code
#endif
#ifdef MG_COMPACT_ABI
#if !defined(MG_SINGLETON) || !defined(MG_SOFT_B)
#error compact ABI requires the single-reader software Type B profile
#endif


#define MG_ENTRY(name) mg_##name
#define MG_SELF_PARAM(type, name)
#define MG_SELF_ONLY(type, name) void
#define MG_OWNER(pointer, owner) (owner)
#define MG_LOCAL __idata
#ifdef __SDCC
#define MG_BOOL __bit
#else
#define MG_BOOL _Bool
#endif
#define MG_CALL
#else
#define MG_ENTRY(name) name
#define MG_SELF_PARAM(type, name) type __xdata *name,
#define MG_SELF_ONLY(type, name) type __xdata *name
#define MG_OWNER(pointer, owner) (pointer)
#define MG_LOCAL
#define MG_BOOL uint8_t
#ifdef __SDCC
#define MG_CALL __reentrant
#else
#define MG_CALL
#endif
#endif
#ifdef MG_UID_PROFILE

void copy_xdata(uint8_t __xdata *dest, const uint8_t __xdata *src, uint16_t n) MG_CALL;
void wipe_xdata(uint8_t __xdata *dest, uint16_t n) MG_CALL;
#endif
#endif
