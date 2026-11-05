/* SPDX-License-Identifier: AGPL-3.0-only */
#ifndef PAKURI_USB_DEVICE_H
#define PAKURI_USB_DEVICE_H
#include "memory.h"
#define USB_EVENT_RESET 1
#define USB_EVENT_OUT 2
#define USB_EVENT_IN 4
#define USB_EVENT_ABORT 8
#define USB_EVENT_FAULT 16
#ifdef __SDCC
extern __xdata __at(0x0000) uint8_t usb_ep0[64];
extern __xdata __at(0x0040) uint8_t usb_ep1[64];
extern __xdata __at(0x0080) uint8_t usb_ep2[128];
#else
extern uint8_t usb_ep0[64], usb_ep1[64], usb_ep2[128];
#endif
extern __data uint8_t usb_configured, usb_out_pending, usb_out_length;
extern __data uint8_t usb_in_armed, usb_abort_pending, usb_abort_sequence;
extern __data uint8_t usb_events;
extern __data uint8_t usb_accept_out;

#if !defined(MG_TIMING) && !defined(MG_UID_PROFILE)
extern __xdata uint8_t usb_abort_snapshot[3];
#endif
void usb_device_init(void);
void usb_device_poll(void);
void usb_device_arm(void);

void usb_release_out(void);
uint8_t usb_bulk_ready(void);
uint8_t usb_send_bulk(uint8_t length);
void usb_notify_slot(uint8_t present);

void usb_abort_complete(void);
void usb_cancel_bulk_in(void);
void usb_allow_abort_reply(void);
uint8_t usb_notification_pending(void);
#endif
