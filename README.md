# PaKuRi

PaKuRi is an independent, open-source contactless smart card reader inspired by
Sony's PaSoRi readers. It uses a CH552 or CH559 microcontroller and a PN532
module to provide USB CCID access through PC/SC. It is not affiliated with Sony
and does not implement PaSoRi-specific USB protocols.

## Support

- **CH552:** ISO-DEP for Type A/B cards and UID retrieval for Type A cards.
- **CH559:** An experimental build that also supports MIFARE Classic read/write
  and Type F reading.

The CH559 release image is an experimental candidate that has not been tested
on hardware. Supported operations depend on the card type. Extended APDUs and
PaSoRi-specific applications are not supported.

## Hardware

Connect a PN532 module configured for HSU/UART to the MCU. Pin numbers below
refer to the IC packages, not board headers. Disconnect power before wiring.

| PN532 | CH552T | CH559T |
| --- | --- | --- |
| VCC | USB 5 V / pin 19 | USB 5 V / pin 19 |
| GND | GND / pin 18 | GND / pin 18 |
| RXD | TX / pin 9 | TX / pin 16 |
| TXD | RX / pin 10 | RX / pin 17 |

Use 5 V only if the PN532 module supports it; check its documentation and
logic levels. Configure the PN532 for UART at 115200 baud, 8N1. Switch settings
vary by module. Provide the MCU's required power supply decoupling capacitors;
on CH559T, VDD33 (pin 20) requires at least 3.3 µF to GND and must not be
connected to 5 V.

## PC setup

On Debian or Ubuntu, install the PC/SC service, CCID driver and diagnostic tool:

```sh
sudo apt install pcscd libccid pcsc-tools
pcsc_scan
```

The development firmware uses USB VID/PID `CAFE:5522`. Your libccid installation
may need an entry for this ID in its supported-reader configuration. In the
CCID bundle's `Info.plist`, add `0xCAFE`, `0x5522` and a reader name at the same
index in the `ifdVendorID`, `ifdProductID` and `ifdFriendlyName` arrays,
respectively, then restart `pcscd`. The bundle location depends on the system.

## Build and test

The build requires SDCC 4.5.0, SDCC uCsim, a C compiler, make, Python 3, and
IntelHex.

```sh
make -C firmware test
make -C firmware ch552-baseline-check
make -C firmware/ch559 standalone-candidate
```

Prebuilt firmware is available on the [Releases](https://github.com/tentaisan/PaKuRi/releases) page.

## Flashing

Download the `.hex` file for your MCU from Releases and check it against
`SHA256SUMS`. The CH559 image is experimental. A USB connection to the MCU and
its factory bootloader are required.

1. Disconnect USB power and enter the bootloader:
   - **CH552T:** Connect a 10 kΩ resistor between D+ (pin 14) and VCC
     (pin 19), then connect USB. Keep the resistor connected while flashing.
   - **CH559T:** Connect P4.6 (pin 9) to GND (pin 18), then connect USB.
     Keep the jumper connected while flashing. Ensure P4.6 is not driven high
     by another circuit.
2. Use [WCHISPTool](https://www.wch-ic.com/downloads/WCHISPTool_Setup_exe.html)
   or another programmer compatible with the MCU and its bootloader. Select the
   correct CH55x model and USB download, load the matching `.hex` file, program
   it and verify the result. Consult the programmer's instructions for the
   supported bootloader and erase range; avoid changing configuration or
   DataFlash settings unintentionally.
3. Disconnect USB, remove the boot connection, and reconnect USB to start the
   firmware normally. Confirm the reader is available through PC/SC.

Pin numbers apply to the IC packages listed above. Use a stable power supply
throughout programming. The exact WCHISPTool procedure has not been validated
for these release images.

## Licenses

See the SPDX identifier in each file. License texts are available in [licenses](licenses/).
