/* SPDX-License-Identifier: AGPL-3.0-only */
/* ManeKey usb_bridge.cのEP0/USB toggle・W1C順序を2026-10-25に改変。
 * HID/Main/鍵管理を除去。上位層とはイベントと単一DMA所有権だけで連携する。 */
#include "usb_device.h"
#ifdef MG_CH559
#include "../ch559/ch559_regs.h"
#else
#include "ch552_regs.h"
#endif
#include "usb_descriptors.h"
#include "reader.h"
#include "timing.h"
#if defined(MG_CH559) && defined(MG_CCID_DIAGNOSTIC)
#include "gate.h"
#endif
extern __xdata Reader reader_state;
#ifdef MG_RESET_DIAGNOSTIC
extern volatile __data uint16_t milliseconds;
#endif

__xdata __at(0x0000) uint8_t usb_ep0[64];
__xdata __at(0x0040) uint8_t usb_ep1[64];
__xdata __at(0x0080) uint8_t usb_ep2[128];
__data uint8_t usb_configured, usb_out_pending, usb_out_length, usb_in_armed;
__data uint8_t usb_abort_pending, usb_abort_sequence, usb_events;
__data uint8_t usb_accept_out;
#if !defined(MG_TIMING) && !defined(MG_UID_PROFILE)
__xdata uint8_t usb_abort_snapshot[3];
#endif
static __bit abort_reply;
static __data uint8_t address_pending, config_pending, control_length, control_offset;


static __bit halt_in, halt_out, halt_notify, notify_armed, notify_dirty, faulted;
static __data uint8_t notify_value;
static const __code uint8_t *control_source;

#if !defined(MG_UID_PROFILE) || (defined(MG_CH559) && defined(MG_CCID_DIAGNOSTIC))


#ifdef CH552_HOST_TEST
extern uint8_t usb_test_iram[256];
#define STACK_START 0x44
#define STACK_BYTE(at) usb_test_iram[at]
#else
extern __idata uint8_t _start__stack;
#define STACK_START ((uint8_t)&_start__stack)
#define STACK_BYTE(at) (*((volatile uint8_t __idata *)(at)))
#endif
static void stack_observation(void) {
    uint8_t at = 255;
    usb_ep0[0] = STACK_START;
    usb_ep0[1] = 0;
    do {
        if (STACK_BYTE(at) != 0xa5) { usb_ep0[1] = at; break; }
    } while (--at >= STACK_START);
}

#endif
#ifdef CH552_HOST_TEST
#define CLEAR_FLAGS(mask) (USB_INT_FG &= (uint8_t)~(mask))
#ifndef USB_AFTER_CLEAR
#define USB_AFTER_CLEAR() ((void)0)
#endif
#define CLEAR_TRANSFER() do { CLEAR_FLAGS(2); USB_AFTER_CLEAR(); } while (0)
#else
#define CLEAR_FLAGS(mask) (USB_INT_FG = (mask))
#define CLEAR_TRANSFER() (UIF_TRANSFER = 0)
#endif

static void reset_transport(void) {
#ifndef MG_UID_PROFILE
    uint8_t i;
#endif
    usb_out_pending = usb_out_length = usb_in_armed = usb_abort_pending = 0;
    usb_accept_out = 1; abort_reply = 0;
    halt_in = halt_out = halt_notify = notify_armed = 0;
    notify_dirty = 1;
#if !defined(MG_TIMING) && !defined(MG_UID_PROFILE)
    usb_abort_snapshot[0] = usb_abort_snapshot[1] = usb_abort_snapshot[2] = 0xff;
#endif
#ifdef MG_UID_PROFILE
    wipe_xdata(usb_ep2,128); wipe_xdata(usb_ep1,64);
#else
    for (i = 0; i < 128; ++i) usb_ep2[i] = 0;
    for (i = 0; i < 64; ++i) usb_ep1[i] = 0;
#endif
    UEP1_T_LEN = UEP2_T_LEN = 0;
    UEP1_CTRL = UEP2_CTRL = 0x0a;
    usb_events = USB_EVENT_RESET;
}
static void stall(void) { UEP0_T_LEN = 0; UEP0_CTRL = 0x0f; }
static void control_next(void) {
    uint8_t i, count = control_length - control_offset;
    if (count > 64) count = 64;
    for (i = 0; i < count; ++i) usb_ep0[i] = control_source[control_offset++];
    UEP0_T_LEN = count; UEP0_CTRL &= 0xc0;
}
static void setup(void) {
    uint8_t type, request, value, high, index, index_hi, length, length_hi, size = 0;
    control_length = control_offset = 0;
    address_pending = config_pending = 0xff;
    if (USB_RX_LEN != 8) { stall(); return; }
    type = usb_ep0[0]; request = usb_ep0[1]; value = usb_ep0[2]; high = usb_ep0[3];
    index = usb_ep0[4]; index_hi = usb_ep0[5]; length = usb_ep0[6]; length_hi = usb_ep0[7];
    UEP0_CTRL = 0xc2;
    if (type == 0x80 && request == 6 && !value && !index && !index_hi) {
        if (high == 1) { control_source = device_descriptor; size = sizeof(device_descriptor); }
        else if (high == 2) { control_source = configuration_descriptor; size = sizeof(configuration_descriptor); }
        else { stall(); return; }
    } else if (type == 0x81 && request == 6 && !value && high == 0x21 && !index && !index_hi) {
        control_source = configuration_descriptor + 18; size = 54;
    } else if (type == 0xa1 && (request == 2 || request == 3) &&
               !value && !high && !index && !index_hi && usb_configured) {
        control_source = request == 2 ? clock_frequency : data_rate; size = 4;
    }
    if (size) {
        control_length = (!length_hi && length < size) ? length : size;
        control_next(); return;
    }
#ifdef MG_UID_PROFILE
    if (type == 0xc0 && !value && !high && !index && !index_hi && !length_hi) {
#if defined(MG_CH559) && defined(MG_CCID_DIAGNOSTIC)
        if (request == 0x5b && length == 2) {
            stack_observation();
        } else
#endif
        if (request == 0x5c && (length == 4 || length == 6)) {
            usb_ep0[0]=reader_state.phase; usb_ep0[1]=reader_state.error; usb_ep0[2]=reader_state.pn.error;
            usb_ep0[3]=reader_state.rf_status;
            if (length == 6) { usb_ep0[4]=reader_state.pn.payload; usb_ep0[5]=reader_state.pn.payload>>8; }
#if defined(MG_CH559) && defined(MG_CCID_DIAGNOSTIC)
        } else if (request == 0x5d && length == 8) {

            usb_ep0[0]=gate_state.job; usb_ep0[1]=gate_state.background;
            usb_ep0[2]=gate_state.rx_closed; usb_ep0[3]=gate_state.active;
            usb_ep0[4]=gate_state.response; usb_ep0[5]=usb_out_pending;
            usb_ep0[6]=usb_accept_out; usb_ep0[7]=faulted;
#ifdef MG_RESET_DIAGNOSTIC
        } else if (request == 0x5e && length == 1) {

            usb_ep0[0]=reader_state.selected ? reader_state.card.type : 0xff;
        } else if (request == 0x60 && (length == 1 || length == 3)) {

            usb_ep0[0]=(PCON >> 4) & 3;
            if (length == 3) {

                do {
                    usb_ep0[2]=(uint8_t)(milliseconds>>8);
                    usb_ep0[1]=(uint8_t)milliseconds;
                } while (usb_ep0[2] != (uint8_t)(milliseconds>>8));
            }
#endif
#ifdef MG_UART_DIAGNOSTIC
        } else if (request == 0x61 && length == 1) {

            usb_ep0[0]=pn_uart_diagnostic;
#endif
#ifdef MG_STANDALONE_SCAN
        } else if (request == 0x5f && length == 3) {

            usb_ep0[0]=reader_state.phase; usb_ep0[1]=reader_state.present != 0;
            usb_ep0[2]=usb_configured != 0;
#endif
#endif
        } else { stall(); return; }
        UEP0_T_LEN=length; UEP0_CTRL=0xc0; return;
#else
    if (type == 0xc0 && !value && !high && !index && !index_hi && !length_hi) {
#ifdef MG_SCAN_DIAGNOSTIC
        if (request == 0x60 && length == 7) {
            uint8_t i;
            for (i = 0; i < 7; ++i) usb_ep0[i] = reader_scan_diagnostic[i];
        } else
#endif
        if (request == 0x5b && length == 2) {
            stack_observation();
#ifndef MG_TIMING
        } else if (request == 0x5c && (length == 4 || length == 6)) {

            usb_ep0[0] = reader_state.phase; usb_ep0[1] = reader_state.error;
            usb_ep0[2] = reader_state.pn.error; usb_ep0[3] = reader_state.rf_status;
            if (length == 6) {
                usb_ep0[4] = (uint8_t)reader_state.pn.payload;
                usb_ep0[5] = reader_state.pn.payload >> 8;
            }
        } else if (request == 0x5d && length == 3) {
            usb_ep0[0] = usb_abort_snapshot[0]; usb_ep0[1] = usb_abort_snapshot[1];
            usb_ep0[2] = usb_abort_snapshot[2];
#endif
        } else if (request == 0x5e && length == 1) {
            usb_ep0[0] = reader_state.selected ? reader_state.card.type : 0xff;
#ifdef MG_TIMING
        } else if (request == 0x5f && length == 4) {

            usb_ep0[0] = (uint8_t)timing_loop_max; usb_ep0[1] = timing_loop_max >> 8;
            usb_ep0[2] = timing_irq_max; usb_ep0[3] = timing_uart_overflow;
#endif
        } else { stall(); return; }
        UEP0_T_LEN = length; UEP0_CTRL = 0xc0; return;
#endif
    } else if (type == 0x21 && request == 1 && !value && !index && !index_hi &&
        !length && !length_hi && usb_configured) {
        if (usb_abort_pending && usb_abort_sequence != high) { stall(); return; }
        if (!usb_abort_pending) abort_reply = 0;
        usb_abort_sequence = high; usb_abort_pending = 1;
        usb_events |= USB_EVENT_ABORT;
        UEP2_CTRL = (UEP2_CTRL & 0xc0) | 0x0a;
    } else if (!type && request == 5 && !high && value <= 127 && !index && !index_hi && !length && !length_hi) {
        address_pending = value;
    } else if (!type && request == 9 && !high && value <= 1 && !index && !index_hi && !length && !length_hi) {
        config_pending = value;
    } else if (type == 0x80 && request == 8 && !value && !high && !index && !index_hi && length == 1 && !length_hi) {
        usb_ep0[0] = usb_configured; UEP0_T_LEN = 1; UEP0_CTRL = 0xc0; return;
    } else if (type == 0x81 && request == 10 && !value && !high && !index && !index_hi &&
               length == 1 && !length_hi && usb_configured) {
        usb_ep0[0] = 0; UEP0_T_LEN = 1; UEP0_CTRL = 0xc0; return;
    } else if (type == 1 && request == 11 && !value && !high && !index && !index_hi &&
               !length && !length_hi && usb_configured) {

    } else if (request == 0 && !value && !high && !index_hi && length == 2 && !length_hi &&
               ((type == 0x80 && !index) || (type == 0x81 && !index && usb_configured) ||
                (type == 0x82 && usb_configured && (index == 0 || index == 0x80 ||
                 index == 2 || index == 0x82 || index == 0x81)))) {
        usb_ep0[0] = type != 0x82 ? 0 :
            (index == 2 ? halt_out : (index == 0x82 ? halt_in : (index == 0x81 ? halt_notify : 0)));
        usb_ep0[1] = 0; UEP0_T_LEN = 2; UEP0_CTRL = 0xc0; return;
    } else if (type == 2 && (request == 1 || request == 3) && !value && !high && !index_hi &&
               (index == 2 || index == 0x82 || index == 0x81) && !length && !length_hi && usb_configured) {
        if (request == 1) {
            if (index == 0x81) {
                halt_notify = notify_armed = 0; notify_dirty = 1;
                UEP1_CTRL = (UEP1_CTRL & 0x80) | 0x0a;
            } else {

                UEP2_CTRL = (UEP2_CTRL & (index == 2 ? 0x40 : 0x80)) | 0x0a;
                if (index == 2) halt_out = 0; else halt_in = 0;
                usb_in_armed = usb_abort_pending = 0; UEP2_T_LEN = 0;
                usb_release_out();
                usb_events = USB_EVENT_RESET;
            }
        }
        else if (index == 2) halt_out = 1;
        else if (index == 0x82) halt_in = 1;
        else halt_notify = 1;
    } else { stall(); return; }
    UEP0_T_LEN = 0; UEP0_CTRL = 0xc0;
}
void usb_device_poll(void) {
    uint8_t state, token, endpoint;
    if (USB_INT_FG & 1) {
        USB_DEV_AD = usb_configured = faulted = 0;
        address_pending = config_pending = 0xff;
        control_length = control_offset = 0;
        reset_transport(); UEP0_CTRL = 2; UEP0_T_LEN = 0;
        CLEAR_FLAGS(0x1f); return;
    }
    if (USB_INT_FG & 0x10) {
        faulted = 1;
        usb_events |= USB_EVENT_FAULT;
        UEP1_CTRL = UEP2_CTRL = 0x0f;
        CLEAR_FLAGS(0x10);
    }
    if (USB_INT_FG & 2) {
        state = USB_INT_ST; token = state & 0x30; endpoint = state & 15;
        if (!endpoint) {
            if (token == 0x30) setup();
            else if (token == 0x20) {
                UEP0_CTRL ^= 0x40;
                if (address_pending != 0xff) { USB_DEV_AD = address_pending; address_pending = 0xff; }
                if (config_pending != 0xff) {
                    usb_configured = config_pending; config_pending = 0xff; reset_transport();
                }
                if (control_offset < control_length) control_next();
                else UEP0_CTRL = (UEP0_CTRL & 0xc0) | 2;
            } else if (!token && (state & 0x40)) {
                if (USB_RX_LEN) stall(); else UEP0_CTRL = 2;
            }
        } else if (endpoint == 2) {
            UEP2_CTRL = (UEP2_CTRL & 0xc0) | 0x0a;
            if (!token && !(state & 0x40)) {                               }
            else if (!token && usb_configured && USB_RX_LEN <= 64 && !usb_out_pending) {
                UEP2_CTRL ^= 0x80;
                usb_out_length = USB_RX_LEN; usb_out_pending = 1;
                usb_events |= USB_EVENT_OUT;
            } else if (token == 0x20 && usb_in_armed) {
                UEP2_CTRL ^= 0x40; usb_in_armed = 0;
                CLEAR_TRANSFER();
                usb_events |= USB_EVENT_IN;
                return;
            } else usb_events |= USB_EVENT_FAULT;
        } else if (endpoint == 1) {
            UEP1_CTRL = (UEP1_CTRL & 0xc0) | 0x0a;
            if (token == 0x20 && notify_armed) {
                UEP1_CTRL ^= 0x40; notify_armed = 0;
            } else usb_events |= USB_EVENT_FAULT;
        } else usb_events |= USB_EVENT_FAULT;
        CLEAR_TRANSFER();
    }
    if (USB_INT_FG & 4) CLEAR_FLAGS(4);
}
void usb_release_out(void) {
#ifdef MG_UID_PROFILE
    wipe_xdata(usb_ep2,64);
#else
    uint8_t i;
    for (i = 0; i < 64; ++i) usb_ep2[i] = 0;
#endif
    usb_out_pending = usb_out_length = 0;
}
uint8_t usb_bulk_ready(void) {
    return usb_configured && !faulted && !usb_in_armed && !halt_in && (!usb_abort_pending || abort_reply);
}
uint8_t usb_send_bulk(uint8_t length) {
    if (length > 64 || !usb_bulk_ready()) return 0;
    UEP2_T_LEN = length; usb_in_armed = 1;
    return 1;
}
void usb_notify_slot(uint8_t present) { notify_value = present ? 3 : 2; notify_dirty = 1; }
void usb_abort_complete(void) { usb_abort_pending = abort_reply = 0; }
void usb_allow_abort_reply(void) { abort_reply = 1; }
void usb_cancel_bulk_in(void) {
    UEP2_CTRL = (UEP2_CTRL & 0xc0) | 0x0a;
    usb_in_armed = 0; UEP2_T_LEN = 0;
}
uint8_t usb_notification_pending(void) { return notify_armed || notify_dirty; }
void usb_device_arm(void) {
    if (!usb_configured || faulted) {
        UEP1_CTRL = UEP2_CTRL = 0x0a; return;
    }
    if (!notify_armed && notify_dirty && !halt_notify) {
        usb_ep1[0] = 0x50; usb_ep1[1] = notify_value;
        UEP1_T_LEN = 2; notify_armed = 1; notify_dirty = 0;
    }
    UEP1_CTRL = (UEP1_CTRL & 0xc0) | (halt_notify ? 3 : (notify_armed ? 0 : 2)) | 8;
    UEP2_CTRL = (UEP2_CTRL & 0xc0) |
        (halt_in ? 3 : (usb_in_armed && (!usb_abort_pending || abort_reply) ? 0 : 2)) |
        (halt_out ? 12 : (usb_out_pending || !usb_accept_out ? 8 : 0));
}
void usb_device_init(void) {
    usb_configured = faulted = 0; notify_value = 2;
    address_pending = config_pending = 0xff; control_length = control_offset = 0;
    UEP4_1_MOD = 0x40; UEP2_3_MOD = 0x0c;
    UEP0_DMA_L = UEP0_DMA_H = UEP1_DMA_H = UEP2_DMA_H = 0;
    UEP1_DMA_L = 0x40; UEP2_DMA_L = 0x80;
    UEP0_CTRL = 2; UEP0_T_LEN = 0; USB_DEV_AD = 0;
    reset_transport(); CLEAR_FLAGS(0x1f); USB_INT_EN = 0;
#ifdef MG_CH559
    UDEV_CTRL = 0x31; USB_CTRL = 0x29;
#else
    UDEV_CTRL = 0x81; USB_CTRL = 0x29;
#endif
}
