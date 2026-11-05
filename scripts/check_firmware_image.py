#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""実機に接続せず、CH552アプリ画像の境界とreset vectorを検査する。"""

import argparse
import hashlib
import json
from pathlib import Path

from intelhex import IntelHex, IntelHexError


APP_SIZE = 0x3800


def checked_image(path):
    image = IntelHex(str(path))
    if image.start_addr is not None:
        raise ValueError("unexpected start-address record for MCS51")
    addresses = set(image.addresses())
    if not addresses:
        raise ValueError("empty image")
    if any(address < 0 or address >= APP_SIZE for address in addresses):
        raise ValueError("image contains data outside app range 0x0000..0x37ff")
    if not {0, 1, 2} <= addresses or image[0] != 0x02:
        raise ValueError("reset vector must contain a complete 8051 LJMP")
    reset_target = (image[1] << 8) | image[2]
    if reset_target < 3 or reset_target not in addresses or image[reset_target] == 0xFF:
        raise ValueError("reset LJMP target must point to populated app code")

    padded = bytes(image[address] if address in addresses else 0xFF
                   for address in range(APP_SIZE))
    return {
        "app_limit_bytes": APP_SIZE,
        "populated_bytes": len(addresses),
        "highest_address": max(addresses),
        "reset_target": reset_target,
        "padded_app_sha256": hashlib.sha256(padded).hexdigest(),
        "qualification": "offline image structure only; not approved for programming",
        "hardware_execution_verified": False,
        "flash_authorized": False,
    }, padded


def inspect_image(path):
    return checked_image(path)[0]


def write_image(path, output):
    output = Path(output)
    report_path = output.with_suffix(".json")
    if len({Path(path).resolve(), output.resolve(), report_path.resolve()}) != 3:
        raise ValueError("input, binary output and JSON report must be distinct")
    report, padded = checked_image(path)
    output.write_bytes(padded)
    report["output_bytes"] = len(padded)
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path, help="Intel HEX (.ihx/.hex)")
    parser.add_argument("--output", type=Path, help="14KiB FF padding binaryと同名JSONを生成する（USB操作なし）")
    args = parser.parse_args()
    try:
        result = write_image(args.image, args.output) if args.output else inspect_image(args.image)
    except (OSError, IntelHexError, ValueError) as exc:
        parser.exit(1, f"image check failed: {exc}\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
