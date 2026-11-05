/* SPDX-License-Identifier: Apache-2.0 */

#define MG_TIMING
static void timing_bookend_hook(void);
#define TIMING_BOOKEND_HOOK() timing_bookend_hook()
#include "usb_harness.c"
static uint8_t bookend_ticks;
static void timing_bookend_hook(void) { TL0 += bookend_ticks; }
#include "../src/timing.c"
#include "../src/uart.c"
#include <assert.h>
#include <string.h>

static void request(uint8_t kind, uint8_t code, uint16_t value, uint16_t index, uint16_t length) {
    usb_ep0[0]=kind; usb_ep0[1]=code;
    usb_ep0[2]=value; usb_ep0[3]=value>>8;
    usb_ep0[4]=index; usb_ep0[5]=index>>8;
    usb_ep0[6]=length; usb_ep0[7]=length>>8;
    test_transfer(0x30,8);
}

int main(int argc, char **argv) {
    uint8_t i;
    assert(argc==2);
    if (!strcmp(argv[1],"init")) {
        T2CON=T2MOD=0xff; TH1=243; TL1=241; TMOD=0x21;
        timing_loop_max=999; timing_irq_max=19; timing_uart_overflow=1;
        timing_init();
        assert(T2CON==0 && T2MOD==0xb0 && TR2==1);
        assert(!RCAP2H && !RCAP2L && !TH2 && !TL2);
        assert(TH1==243 && TL1==241 && TMOD==0x21);
        assert(!timing_loop_max && !timing_irq_max && !timing_uart_overflow);
    } else if (!strcmp(argv[1],"poll")) {
        timing_init(); EA=1; TF2=0; TH2=1; TL2=2;
        timing_poll(); assert(timing_loop_max==260 && EA==1 && TR2==1 && !TH2 && !TL2);
        EA=0; TH2=0; TL2=255; timing_poll();
        assert(timing_loop_max==260 && EA==0);
        bookend_ticks=10; TL0=250; TH2=1; TL2=2;
        timing_poll(); assert(timing_loop_max==270 && TL0==4 && EA==0);
        TH2=0xfe; TL2=0; TF2=0; timing_poll();assert(timing_loop_max==0xffff);
        timing_init(); bookend_ticks=255; TH2=0xfd; TL2=255; TF2=0;
        timing_poll();assert(timing_loop_max==0xff00);
        TF2=1; TH2=0; TL2=1; timing_poll();
        assert(timing_loop_max==0xffff && !TF2);
        TF2=0; TH2=0; TL2=2; timing_poll();assert(timing_loop_max==0xffff);
    } else if (!strcmp(argv[1],"irq")) {
        timing_init(); TH0=0; TL0=8; TIMING_IRQ_SAMPLE(); assert(timing_irq_max==8);
        TL0=2; TIMING_IRQ_SAMPLE(); assert(timing_irq_max==8);
        TH0=1; TL0=0; TIMING_IRQ_SAMPLE(); assert(timing_irq_max==255);
        TH0=0; TL0=9; TIMING_IRQ_SAMPLE(); assert(timing_irq_max==255);
    } else if (!strcmp(argv[1],"uart")) {
        uart_init(); timing_init();
        for (i=0;i<63;++i) {SBUF=i; RI=1; serial_interrupt();}
        assert(!timing_uart_overflow && !uart_faulted());
        SBUF=63; RI=1; serial_interrupt();assert(timing_uart_overflow && uart_faulted());
        uart_reset();assert(timing_uart_overflow && !uart_faulted());
        timing_init();assert(!timing_uart_overflow);
    } else if (!strcmp(argv[1],"usb")) {
        test_usb_init(); timing_loop_max=0x1234; timing_irq_max=7; timing_uart_overflow=1;
        request(0xc0,0x5f,0,0,4);
        assert(UEP0_T_LEN==4 && UEP0_CTRL==0xc0);
        assert(usb_ep0[0]==0x34 && usb_ep0[1]==0x12 && usb_ep0[2]==7 && usb_ep0[3]==1);
        request(0xc0,0x5d,0,0,3);assert(UEP0_CTRL==0x0f);
        request(0xc0,0x5c,0,0,4);assert(UEP0_CTRL==0x0f);
        request(0xc0,0x5c,0,0,6);assert(UEP0_CTRL==0x0f);
        request(0xc1,0x5f,0,0,4);assert(UEP0_CTRL==0x0f);
        request(0x40,0x5f,0,0,4);assert(UEP0_CTRL==0x0f);
        request(0xc0,0x5f,1,0,4);assert(UEP0_CTRL==0x0f);
        request(0xc0,0x5f,0,1,4);assert(UEP0_CTRL==0x0f);
        request(0xc0,0x5f,0,0,3);assert(UEP0_CTRL==0x0f);
        request(0xc0,0x5f,0,0,0x104);assert(UEP0_CTRL==0x0f);
        test_reset();assert(timing_loop_max==0x1234 && timing_irq_max==7 && timing_uart_overflow);
    } else return 2;
    return 0;
}
