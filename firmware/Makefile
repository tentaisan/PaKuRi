# SPDX-License-Identifier: AGPL-3.0-only

SDCC ?= sdcc
PYTHON ?= /usr/bin/python3
TIMING ?= 0
RAW_B_COMPARE ?= 0
RF_WAIT ?= 0
SOFT_B ?= 0
COMPACT ?= 0
SCAN_DIAGNOSTIC ?= 0
UID_PROFILE ?= 0
ifneq ($(filter $(UID_PROFILE),0 1),$(UID_PROFILE))
$(error UID_PROFILE must be 0 or 1)
endif
ifeq ($(UID_PROFILE),1)
ifneq ($(SOFT_B)$(COMPACT)$(SCAN_DIAGNOSTIC)$(RAW_B_COMPARE)$(TIMING)$(RF_WAIT),110000)
$(error UID_PROFILE requires the compact software B profile only)
endif
endif
ifneq ($(filter $(SCAN_DIAGNOSTIC),0 1),$(SCAN_DIAGNOSTIC))
$(error SCAN_DIAGNOSTIC must be 0 or 1)
endif
ifeq ($(SCAN_DIAGNOSTIC),1)
ifneq ($(SOFT_B)$(COMPACT)$(RAW_B_COMPARE)$(TIMING)$(RF_WAIT),00000)
$(error SCAN_DIAGNOSTIC requires its own normal ABI profile)
endif
endif
ifneq ($(filter $(COMPACT),0 1),$(COMPACT))
$(error COMPACT must be 0 or 1)
endif
ifeq ($(COMPACT),1)
ifneq ($(SOFT_B),1)
$(error COMPACT requires SOFT_B=1)
endif
endif
ifneq ($(filter $(SOFT_B),0 1),$(SOFT_B))
$(error SOFT_B must be 0 or 1)
endif
ifeq ($(SOFT_B),1)
ifneq ($(RAW_B_COMPARE)$(TIMING)$(RF_WAIT),000)
$(error SOFT_B requires its own profile)
endif
endif
ifneq ($(filter $(RF_WAIT),0 1),$(RF_WAIT))
$(error RF_WAIT must be 0 or 1)
endif
ifeq ($(RF_WAIT),1)
ifneq ($(RAW_B_COMPARE)$(TIMING),00)
$(error RF_WAIT requires the normal automatic exchange profile)
endif
endif
ifneq ($(filter $(RAW_B_COMPARE),0 1 2 3),$(RAW_B_COMPARE))
$(error RAW_B_COMPARE must be 0, 1, 2 or 3)
endif
ifneq ($(RAW_B_COMPARE),0)
ifneq ($(TIMING),0)
$(error raw comparison and timing profiles cannot be combined)
endif
endif
ifneq ($(filter $(TIMING),0 1),$(TIMING))
$(error TIMING must be 0 or 1)
endif
OUT := $(abspath ../build/firmware$(if $(filter 1,$(TIMING)),-timing,))
ifeq ($(TIMING),1)
ifeq ($(filter %-timing,$(OUT)),)
$(error TIMING=1 requires a dedicated OUT ending in -timing)
endif
else
ifneq ($(filter %-timing,$(OUT)),)
$(error the -timing output is reserved for TIMING=1)
endif
endif
ifeq ($(SCAN_DIAGNOSTIC),1)
ifeq ($(filter %-scan-diagnostic,$(OUT)),)
$(error SCAN_DIAGNOSTIC requires a dedicated OUT ending in -scan-diagnostic)
endif
else
ifneq ($(filter %-scan-diagnostic,$(OUT)),)
$(error the -scan-diagnostic output is reserved for SCAN_DIAGNOSTIC=1)
endif
endif
ifeq ($(UID_PROFILE),1)
ifeq ($(filter %-uid-compact-soft-b,$(OUT)),)
$(error UID_PROFILE requires a dedicated OUT ending in -uid-compact-soft-b)
endif
else
ifneq ($(filter %-uid-compact-soft-b,$(OUT)),)
$(error the -uid-compact-soft-b output is reserved for UID_PROFILE=1)
endif
endif
SRC := $(abspath src)
ifeq ($(COMPACT),1)
ifeq ($(filter %-compact-soft-b,$(OUT)),)
$(error COMPACT requires a dedicated OUT ending in -compact-soft-b)
endif
else
ifneq ($(filter %-compact-soft-b,$(OUT)),)
$(error the -compact-soft-b output is reserved for COMPACT=1)
endif
endif
ifeq ($(SOFT_B),1)
ifeq ($(filter %-soft-b,$(OUT)),)
$(error SOFT_B requires a dedicated OUT ending in -soft-b)
endif
else
ifneq ($(filter %-soft-b,$(OUT)),)
$(error the -soft-b output is reserved for SOFT_B=1)
endif
endif
ifeq ($(RF_WAIT),1)
ifeq ($(filter %-rf-wait,$(OUT)),)
$(error RF_WAIT requires a dedicated OUT ending in -rf-wait)
endif
else
ifneq ($(filter %-rf-wait,$(OUT)),)
$(error the -rf-wait output is reserved for RF_WAIT=1)
endif
endif
ifneq ($(RAW_B_COMPARE),0)
RAW_SUFFIX := $(if $(filter 3,$(RAW_B_COMPARE)),raw-b-timed,$(if $(filter 2,$(RAW_B_COMPARE)),raw-b-control,raw-b-compare))
ifeq ($(filter %-$(RAW_SUFFIX),$(OUT)),)
$(error raw comparison requires a dedicated OUT ending in -$(RAW_SUFFIX))
endif
else
ifneq ($(filter %-raw-b-compare %-raw-b-control %-raw-b-timed,$(OUT)),)
$(error raw comparison output is reserved for a diagnostic profile)
endif
endif
FLAGS := -mmcs51 --model-small --std-sdcc11 --opt-code-size -DMG_SINGLETON \
         --code-loc 0 --code-size 14336 --iram-size 256 --stack-size $(if $(filter 1,$(COMPACT)),64,128) \
         --xram-loc 256 --xram-size 768
ifeq ($(UID_PROFILE),1)
FLAGS += -DMG_UID_PROFILE --noinvariant --noinduction
endif
ifeq ($(SCAN_DIAGNOSTIC),1)
FLAGS += -DMG_SCAN_DIAGNOSTIC
endif
ifeq ($(COMPACT),1)
FLAGS += -DMG_COMPACT_ABI
endif
ifeq ($(SOFT_B),1)
FLAGS += -DMG_SOFT_B
endif
ifeq ($(RF_WAIT),1)
FLAGS += -DMG_RF_WAIT
endif
ifeq ($(TIMING),1)
FLAGS += -DMG_TIMING
endif
ifneq ($(RAW_B_COMPARE),0)
FLAGS += -DMG_RAW_B_COMPARE
endif
ifneq ($(filter $(RAW_B_COMPARE),2 3),)
FLAGS += -DMG_RAW_B_CONTROL
endif
ifeq ($(RAW_B_COMPARE),3)
FLAGS += -DMG_RAW_B_TIMED
endif
OBJECTS := $(OUT)/ccid_packet.rel $(OUT)/pn532_frame.rel $(OUT)/uart.rel $(OUT)/pn532_transport.rel $(OUT)/usb_device.rel $(OUT)/card.rel $(OUT)/reader.rel $(OUT)/timing.rel
ifeq ($(SOFT_B),1)
OBJECTS += $(OUT)/isodep_b.rel
endif
RUNTIME_OBJECTS := $(filter-out $(OUT)/ccid_packet.rel,$(OBJECTS)) $(OUT)/ccid_tx.rel $(OUT)/gate.rel
RUNTIME_ASM := $(OUT)/pakuri.asm $(RUNTIME_OBJECTS:.rel=.asm)
.DELETE_ON_ERROR:
.PHONY: all capacity runtime test classic-core-check ch552-baseline-check
all: runtime
capacity: $(OUT)/capacity_probe.ihx
runtime: $(OUT)/pakuri.ihx
	$(PYTHON) ../scripts/check_stack.py --memory-report "$(OUT)/pakuri.mem" \
	    $(if $(filter 1,$(COMPACT)),--require-leaf-interrupts,) \
	    --image "$<" --output "$(OUT)/pakuri.stack.json" $(RUNTIME_ASM)
	$(PYTHON) ../scripts/check_firmware_image.py "$<" --output "$(OUT)/pakuri.bin"
ifeq ($(TIMING),1)
	$(PYTHON) ../scripts/check_timing_window.py --assembly "$(OUT)/timing.asm" \
	    --image "$(OUT)/pakuri.bin" --stack-report "$(OUT)/pakuri.stack.json" \
	    --output "$(OUT)/pakuri.timing.json"
endif

$(OUT):
	mkdir -p "$@"

$(OUT)/%.rel: src/%.c $(wildcard src/*.h) Makefile | $(OUT)
	cd "$(OUT)" && $(SDCC) $(FLAGS) -c "$(SRC)/$*.c" -o "$@"

$(OUT)/ccid_tx.rel: src/ccid_packet.c $(wildcard src/*.h) Makefile | $(OUT)
	cd "$(OUT)" && $(SDCC) $(FLAGS) -DMG_CCID_TX_ONLY -c "$(SRC)/ccid_packet.c" -o "$@"

$(OUT)/pakuri.ihx: src/main.c $(RUNTIME_OBJECTS) $(wildcard src/*.h) Makefile
	cd "$(OUT)" && $(SDCC) $(FLAGS) "$(SRC)/main.c" $(RUNTIME_OBJECTS) -o "$@"
	$(PYTHON) ../scripts/check_firmware_image.py "$@"

$(OUT)/capacity_probe.ihx: src/capacity_probe.c $(OBJECTS) $(wildcard src/*.h) Makefile
	cd "$(OUT)" && $(SDCC) $(FLAGS) "$(SRC)/capacity_probe.c" $(OBJECTS) -o "$@"
	$(PYTHON) ../scripts/check_firmware_image.py "$@"

test:
	$(PYTHON) -m unittest discover -s tests -p 'test_*.py'
	$(PYTHON) -m unittest discover -s ../scripts -p 'test_*.py'


classic-core-check:
	mkdir -p ../build/classic-core-check
	cd ../build/classic-core-check && $(SDCC) -mmcs51 --model-small --std-sdcc11 \
	    -c ../../firmware/experimental/mifare/classic.c -o classic.rel
	$(PYTHON) -m unittest discover -s tests -p 'test_classic_experimental.py'
	PYTHONPATH=tests $(PYTHON) -m unittest test_classic_bridge.ClassicBridgeTests


ch552-baseline-check:
	$(MAKE) UID_PROFILE=1 SOFT_B=1 COMPACT=1 \
	    OUT=$(abspath ../build/firmware-uid-compact-soft-b) runtime
	@printf '%s  %s\n' 83162abdfc0138a86d37daf55bdcfc44cf553d249ba486dba673a067e48da5ea \
	    $(abspath ../build/firmware-uid-compact-soft-b/pakuri.bin) | sha256sum -c -
