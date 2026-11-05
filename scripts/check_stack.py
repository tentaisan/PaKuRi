#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""SDCC mcs51生成ASMのstack操作・呼出graphを保守的に検査する。実機には接続しない。"""

import argparse
from collections import deque
from dataclasses import dataclass, field
import json
import hashlib
from pathlib import Path
import re


class StackError(ValueError):
    pass


@dataclass
class Function:
    module: str
    name: str
    instructions: list = field(default_factory=list)
    labels: dict = field(default_factory=dict)


def parse_assembly(path):
    functions = []
    active = None
    in_code = False
    for line_number, raw in enumerate(Path(path).read_text().splitlines(), 1):
        text = raw.split(";", 1)[0].strip()
        if not text:
            continue
        if text.startswith(".area"):
            in_code = text.split()[1] == "CSEG"
            active = None
            continue
        if not in_code:
            continue
        match = re.match(r"^([\w$]+):\s*(.*)$", text)
        if match:
            label, text = match.groups()
            if label.startswith("_"):
                active = Function(Path(path).stem, label)
                functions.append(active)
            if active is not None:
                active.labels[label] = len(active.instructions)
        if not text or active is None or "=" in text:
            continue
        if text.startswith("."):
            raise StackError(f"unsupported code directive: {path}:{line_number}: {text}")
        parts = text.lower().split(None, 1)

        operand = text.split(None, 1)[1] if len(parts) > 1 else ""
        active.instructions.append((parts[0], [x.strip() for x in operand.split(",")] if operand else [], line_number))
    return functions


def immediate(value):
    if not value.startswith("#"):
        return None
    try:
        number = int(value[1:], 0)
    except ValueError:
        return None
    if not 0 <= number <= 255:
        return None
    return number if number < 128 else number - 256


def local_stack(function):
    """SP/BPとSP由来のACCだけを追跡。分岐条件は両方とも到達可能と扱う。"""
    instructions, labels = function.instructions, function.labels
    work = deque([(0, 0, None, None, ())])
    seen = {}
    visits = {}
    calls = set()
    peak = 0
    interrupt = False
    while work:
        at, sp, bp, accumulator, saved_bp = work.popleft()
        if not 0 <= at < len(instructions):
            raise StackError(f"falls out of function {function.name}")
        if not 0 <= sp <= 255:
            raise StackError(f"unbalanced/unbounded SP in {function.name}: {sp}")
        key = (at, sp, bp, saved_bp)
        if key in seen:
            old = seen[key]
            if old == accumulator or old is None:
                continue
            accumulator = None
        else:
            visits[at] = visits.get(at, 0) + 1
            if visits[at] > 8:
                raise StackError(f"unbounded stack loop in {function.name}")
        seen[key] = accumulator
        op, operands, line = instructions[at]
        lower = [x.lower() for x in operands]
        context = f"{function.module}:{line} {function.name}"
        successors = [at + 1]
        if lower and lower[0] in ("sp", "_sp", "_bp") and op not in ("mov", "push", "pop", "inc", "dec"):
            raise StackError(f"unsupported stack write: {context}")
        if op == "push":
            sp += 1
            if lower[0] == "_bp":
                saved_bp += ((sp, bp),)
        elif op == "pop":
            if lower[0] == "_bp":
                matches = [value for position, value in saved_bp if position == sp]
                if len(matches) != 1:
                    raise StackError(f"BP restored from unverified byte: {context}")
                bp = matches[0]
            sp -= 1
            if lower[0] in ("a", "acc"):
                accumulator = None
        elif op == "mov":
            destination, source = lower
            if destination in ("sp", "_sp"):
                value = bp if source == "_bp" else accumulator if source in ("a", "acc") else None
                if value is None:
                    raise StackError(f"unknown SP assignment: {context}")
                sp = value
            elif destination == "_bp":
                value = sp if source in ("sp", "_sp") else accumulator if source in ("a", "acc") else None
                if value is None:
                    raise StackError(f"unknown BP assignment: {context}")
                bp = value
            elif destination in ("a", "acc"):
                accumulator = sp if source in ("sp", "_sp") else bp if source == "_bp" else None
        elif op in ("inc", "dec"):
            delta = 1 if op == "inc" else -1
            if lower[0] in ("sp", "_sp"):
                sp += delta
            elif lower[0] in ("a", "acc") and accumulator is not None:
                accumulator += delta
            elif lower[0] == "_bp":
                raise StackError(f"unsupported BP arithmetic: {context}")
        elif op == "add" and lower[0] in ("a", "acc"):
            value = immediate(operands[1])
            accumulator = accumulator + value if accumulator is not None and value is not None else None
        elif op == "xch" and lower[0] in ("a", "acc"):
            if lower[1] == "_bp":
                accumulator, bp = bp, accumulator
            else:
                accumulator = None
        elif op in ("addc", "subb", "mul", "div", "da", "rl", "rr", "rlc", "rrc", "swap"):
            accumulator = None
        elif op in ("movx", "movc", "anl", "orl", "xrl", "clr", "cpl"):
            if lower and lower[0] in ("a", "acc", "ab"):
                accumulator = None
        elif op in ("lcall", "acall"):
            calls.add((operands[0], sp, False))
            accumulator = None
        elif op in ("ret", "reti"):
            if sp != 0 or bp is not None:
                raise StackError(f"unbalanced return SP={sp}/BP={bp}: {context}")
            interrupt |= op == "reti"
            successors = []
        elif op in ("sjmp", "ljmp", "ajmp", "jz", "jnz", "jc", "jnc", "jb", "jnb", "jbc", "cjne", "djnz"):
            target = operands[-1]
            conditional = op not in ("sjmp", "ljmp", "ajmp")
            successors = [at + 1] if conditional else []
            if target in labels:
                successors.append(labels[target])
            elif target.startswith("_"):
                if sp != 0 or bp is not None:
                    raise StackError(f"tail call with live stack SP={sp}: {context}")
                calls.add((target, sp, True))
            else:
                raise StackError(f"unknown branch {target}: {context}")
            if op == "djnz" and lower[0] in ("sp", "_sp", "_bp"):
                raise StackError(f"unsupported stack branch: {context}")
            if op == "djnz" and lower[0] in ("a", "acc"):
                accumulator = accumulator - 1 if accumulator is not None else None
            if op == "jbc" and lower[0].startswith(("acc.", "a.")):
                accumulator = None
        elif op in ("nop", "setb"):
            pass
        else:
            raise StackError(f"unsupported instruction {op}: {context}")
        peak = max(peak, sp)
        saved_bp = tuple((position, value) for position, value in saved_bp if position <= sp)
        work.extend((target, sp, bp, accumulator, saved_bp) for target in successors)
    return peak, calls, interrupt


def analyze(paths, stack_start, reserved=128, require_leaf_interrupts=False):
    if not 0 <= stack_start < 256 or not 0 < reserved <= 256 or stack_start + reserved > 256:
        raise StackError("invalid physical stack region")
    functions = {}
    by_name = {}
    for path in paths:
        for function in parse_assembly(path):
            key = (function.module, function.name)
            if key in functions:
                raise StackError(f"duplicate function {key}")
            functions[key] = function
            by_name.setdefault(function.name, []).append(key)
    locals_ = {key: local_stack(function) for key, function in functions.items()}

    def resolve(module, name):
        if (module, name) in functions:
            return module, name
        candidates = by_name.get(name, [])
        if len(candidates) != 1:
            raise StackError(f"unresolved/ambiguous call {module}:{name}")
        return candidates[0]

    memo, visiting = {}, set()

    def depth(key):
        if key in memo:
            return memo[key]
        if key in visiting:
            raise StackError(f"recursive call graph: {key}")
        visiting.add(key)
        local, calls, _ = locals_[key]
        maximum, path = local, [key[1]]
        for name, sp, tail in calls:
            child, chain = depth(resolve(key[0], name))
            value = sp + (0 if tail else 2) + child
            if value > maximum:
                maximum, path = value, [key[1]] + chain
        visiting.remove(key)
        memo[key] = maximum, path
        return maximum, path

    main, chain = depth(resolve("", "_main"))
    interrupts = {}
    for key, (_, _, is_interrupt) in locals_.items():
        if is_interrupt:
            if require_leaf_interrupts and locals_[key][1]:
                raise StackError(f"non-leaf interrupt cannot use foreground-only ABI: {key[1]}")
            maximum, _ = depth(key)
            interrupts[key[1]] = maximum + 2
    if set(interrupts) != {"_serial_interrupt", "_timer0_interrupt"}:
        raise StackError(f"unexpected interrupt set: {sorted(interrupts)}")

    total = main + sum(interrupts.values())
    if total > reserved or stack_start + total > 256:
        raise StackError(f"stack bound {total} exceeds reserved/physical RAM at {stack_start:#x}")
    return {
        "foreground_bytes": main,
        "foreground_path": chain,
        "interrupt_bytes_including_pc": interrupts,
        "conservative_nested_bound_bytes": total,
        "stack_start": stack_start,
        "reserved_bytes": reserved,
        "reserved_margin_bytes": reserved - total,
        "functions_analyzed": len(functions),
        "reachable_functions": len(memo),
        "assumptions": "SDCC mcs51 ABI; only UART0/Timer0 interrupts; generated ASM not modified; no indirect calls",
        "hardware_execution_verified": False,
        "leaf_interrupts_required": require_leaf_interrupts,
    }


def memory_layout(path):
    match = re.search(r"Stack starts at:\s*(0x[0-9a-fA-F]+).*with\s+(\d+) bytes available", Path(path).read_text())
    if not match:
        raise StackError("missing SDCC stack layout")
    return int(match[1], 16), int(match[2])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("asm", type=Path, nargs="+")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--stack-start", type=lambda value: int(value, 0))
    group.add_argument("--memory-report", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--image", type=Path)
    parser.add_argument("--require-leaf-interrupts", action="store_true",
                        help="reject every ISR call/tail-call for a foreground-only static ABI")
    args = parser.parse_args()
    try:
        reserved = 128
        start = args.stack_start
        if args.memory_report:
            start, reserved = memory_layout(args.memory_report)
        result = analyze(args.asm, start, reserved, args.require_leaf_interrupts)
        result["assembly_sha256"] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in args.asm}
        if args.memory_report:
            result["memory_report_sha256"] = hashlib.sha256(args.memory_report.read_bytes()).hexdigest()
        if args.image:
            from check_firmware_image import inspect_image
            result["image_padded_sha256"] = inspect_image(args.image)["padded_app_sha256"]
        if args.output:
            args.output.write_text(json.dumps(result, indent=2) + "\n")
    except (OSError, StackError) as exc:
        parser.exit(1, f"stack check failed: {exc}\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
