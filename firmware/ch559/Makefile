# SPDX-License-Identifier: AGPL-3.0-only

SDCC ?= sdcc
PYTHON ?= /usr/bin/python3
ROOT := $(abspath ../..)
SRC := $(ROOT)/firmware/src
OUT ?= $(ROOT)/build/ch559-uid-candidate
FLAGS := -mmcs51 --model-small --std-sdcc11 --opt-code-size \
    --code-loc 0 --code-size 61440 --iram-size 256 --stack-size 64 \
    --xram-loc 256 --xram-size 5888 \
    -DMG_CH559 -DMG_SINGLETON -DMG_SOFT_B -DMG_COMPACT_ABI -DMG_UID_PROFILE -DMG_EVENTS \
    --noinvariant --noinduction
NAMES := pn532_frame uart pn532_transport usb_device card reader timing isodep_b gate events
OBJECTS := $(addprefix $(OUT)/,$(addsuffix .rel,$(NAMES))) $(OUT)/ccid_tx.rel
ifeq ($(CLASSIC_LINK),1)
OBJECTS += $(OUT)/classic.rel
endif
ifeq ($(CLASSIC_RUNTIME),1)
FLAGS += -DMG_CLASSIC_STACK_AUTO -DMG_CH559_CLASSIC
endif
ifeq ($(FELICA_RUNTIME),1)
FLAGS += -DMG_CH559_FELICA
OBJECTS += $(OUT)/felica_read.rel
endif
ifeq ($(CCID_DIAGNOSTIC),1)
FLAGS += -DMG_CCID_DIAGNOSTIC
endif
ifeq ($(RESET_DIAGNOSTIC),1)
FLAGS += -DMG_RESET_DIAGNOSTIC
endif
ifeq ($(UART_DIAGNOSTIC),1)
ifneq ($(CCID_DIAGNOSTIC),1)
$(error UART_DIAGNOSTIC requires CCID_DIAGNOSTIC=1)
endif
FLAGS += -DMG_UART_DIAGNOSTIC
endif
ifeq ($(CLASSIC_4K),1)
FLAGS += -DMG_CLASSIC_4K
endif
ifeq ($(CLASSIC_7B),1)
FLAGS += -DMG_CLASSIC_7B
endif
ifeq ($(STANDALONE_OBSERVER),1)
FLAGS += -DMG_STANDALONE_OBSERVER
OBJECTS += $(OUT)/standalone_state.rel $(OUT)/standalone_observer.rel
endif
ifeq ($(DISPATCH),1)
ifneq ($(STANDALONE_OBSERVER),1)
$(error DISPATCH requires STANDALONE_OBSERVER=1)
endif
FLAGS += -DMG_STANDALONE_DISPATCH
OBJECTS += $(OUT)/standalone_dispatch.rel
endif
ifeq ($(STANDALONE_SCAN),1)
FLAGS += -DMG_STANDALONE_SCAN
endif
ASM := $(OUT)/pakuri.asm $(OBJECTS:.rel=.asm)


STANDALONE_FEATURES := CLASSIC_LINK=1 CLASSIC_RUNTIME=1 FELICA_RUNTIME=1 \
    CLASSIC_4K=1 CLASSIC_7B=1 CCID_DIAGNOSTIC=1 RESET_DIAGNOSTIC=1 \
    UART_DIAGNOSTIC=1 STANDALONE_OBSERVER=1 STANDALONE_SCAN=1
.DELETE_ON_ERROR:
.PHONY: candidate classic-linkcheck classic-experimental felica-experimental felica-diagnostic felica-4k felica-4k-7b standalone-observer integrated-experimental recovery-experimental standalone-candidate
classic-linkcheck:
	$(MAKE) CLASSIC_LINK=1 OUT=$(ROOT)/build/ch559-classic-linkcheck candidate
classic-experimental:
	$(MAKE) CLASSIC_LINK=1 CLASSIC_RUNTIME=1 OUT=$(ROOT)/build/ch559-classic-experimental candidate
felica-experimental:
	$(MAKE) CLASSIC_LINK=1 CLASSIC_RUNTIME=1 FELICA_RUNTIME=1 OUT=$(ROOT)/build/ch559-felica-experimental candidate
felica-diagnostic:
	$(MAKE) CLASSIC_LINK=1 CLASSIC_RUNTIME=1 FELICA_RUNTIME=1 CCID_DIAGNOSTIC=1 OUT=$(ROOT)/build/ch559-felica-diagnostic candidate
felica-4k:
	$(MAKE) CLASSIC_LINK=1 CLASSIC_RUNTIME=1 FELICA_RUNTIME=1 CLASSIC_4K=1 OUT=$(ROOT)/build/ch559-felica-4k candidate
felica-4k-7b:
	$(MAKE) CLASSIC_LINK=1 CLASSIC_RUNTIME=1 FELICA_RUNTIME=1 CLASSIC_4K=1 CLASSIC_7B=1 OUT=$(ROOT)/build/ch559-felica-4k-7b candidate
standalone-observer:
	$(MAKE) CLASSIC_LINK=1 CLASSIC_RUNTIME=1 FELICA_RUNTIME=1 STANDALONE_OBSERVER=1 OUT=$(ROOT)/build/ch559-standalone-observer candidate
integrated-experimental:
	$(MAKE) CLASSIC_LINK=1 CLASSIC_RUNTIME=1 FELICA_RUNTIME=1 CLASSIC_4K=1 CLASSIC_7B=1 CCID_DIAGNOSTIC=1 STANDALONE_OBSERVER=1 OUT=$(ROOT)/build/ch559-integrated-experimental candidate
recovery-experimental:
	$(MAKE) CLASSIC_LINK=1 CLASSIC_RUNTIME=1 FELICA_RUNTIME=1 CLASSIC_4K=1 CLASSIC_7B=1 CCID_DIAGNOSTIC=1 STANDALONE_OBSERVER=1 OUT=$(ROOT)/build/ch559-recovery-experimental candidate
standalone-candidate:
	$(MAKE) $(STANDALONE_FEATURES) DISPATCH=1 OUT=$(ROOT)/build/ch559-standalone-candidate candidate
candidate: $(OUT)/pakuri.ihx
	$(PYTHON) $(ROOT)/scripts/check_stack.py --memory-report "$(OUT)/pakuri.mem" \
	    --require-leaf-interrupts --output "$(OUT)/pakuri.stack.json" $(ASM)
	$(PYTHON) $(ROOT)/scripts/check_ch559_candidate.py "$<" --output "$(OUT)/pakuri.bin"

$(OUT):
	mkdir -p "$@"
$(OUT)/%.rel: $(SRC)/%.c $(wildcard $(SRC)/*.h) ch559_regs.h Makefile | $(OUT)
	cd "$(OUT)" && $(SDCC) $(FLAGS) -c "$(SRC)/$*.c" -o "$@"
$(OUT)/ccid_tx.rel: $(SRC)/ccid_packet.c $(wildcard $(SRC)/*.h) ch559_regs.h Makefile | $(OUT)
	cd "$(OUT)" && $(SDCC) $(FLAGS) -DMG_CCID_TX_ONLY -c "$<" -o "$@"
$(OUT)/classic.rel: $(ROOT)/firmware/experimental/mifare/classic.c $(ROOT)/firmware/experimental/mifare/classic.h Makefile | $(OUT)
	cd "$(OUT)" && $(SDCC) $(FLAGS) --stack-auto -c "$<" -o "$@"
$(OUT)/felica_read.rel: $(ROOT)/firmware/experimental/felica/read.c $(ROOT)/firmware/experimental/felica/read.h Makefile | $(OUT)
	cd "$(OUT)" && $(SDCC) $(FLAGS) --stack-auto -c "$<" -o "$@"
$(OUT)/standalone_%.rel: $(ROOT)/firmware/experimental/standalone/%.c $(wildcard $(ROOT)/firmware/experimental/standalone/*.h) Makefile | $(OUT)
	cd "$(OUT)" && $(SDCC) $(FLAGS) --stack-auto -c "$<" -o "$@"
$(OUT)/pakuri.ihx: $(SRC)/main.c $(OBJECTS) $(wildcard $(SRC)/*.h) $(wildcard $(ROOT)/firmware/experimental/standalone/*.h) ch559_regs.h Makefile
	cd "$(OUT)" && $(SDCC) $(FLAGS) "$(SRC)/main.c" $(OBJECTS) -o "$@"
