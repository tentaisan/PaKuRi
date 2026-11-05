#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Offline CH559 candidate structure check. Does not authorize programming."""
import argparse
import hashlib
import json
from pathlib import Path
from intelhex import IntelHex

APP_SIZE = 0xf000


def checked_image(path):
    image = IntelHex(str(path))
    addresses = set(image.addresses())
    if image.start_addr is not None or not addresses or min(addresses) < 0 or max(addresses) >= APP_SIZE:
        raise ValueError('image outside candidate application range')
    if not {0, 1, 2} <= addresses or image[0] != 2:
        raise ValueError('complete LJMP reset vector required')
    reset = image[1] << 8 | image[2]
    if reset < 3 or reset not in addresses or image[reset] == 255:
        raise ValueError('reset target is not populated')
    binary = bytes(image[i] if i in addresses else 255 for i in range(APP_SIZE))
    report = {'candidate_app_limit_bytes': APP_SIZE, 'highest_address': max(addresses),
              'populated_bytes': len(addresses), 'reset_target': reset,
              'sha256_padded': hashlib.sha256(binary).hexdigest(),
              'hardware_execution_verified': False, 'flash_authorized': False}
    return report, binary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image', type=Path); parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report, binary = checked_image(args.image)
    if args.image.resolve() == args.output.resolve(): raise ValueError('output must differ from input')
    args.output.write_bytes(binary)
    print(json.dumps(report, indent=2))


if __name__ == '__main__': main()
