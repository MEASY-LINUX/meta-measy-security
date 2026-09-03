#!/usr/bin/env python3
"""Generate i.MX8MP HABv4 U-Boot fuse commands from CST SRK fuses.

The CST ``SRK_1_2_3_4_fuse.bin`` file contains the 256-bit SRK hash as eight
little-endian uint32 values.  i.MX8MP stores the first four words in OCOTP
bank 6, words 0..3, and the remaining four in bank 7, words 0..3.  The close
operation is represented as a normal U-Boot ``fuse prog`` command for
SEC_CONFIG (bank 1, word 3, bit 25).

Fuse programming is irreversible.  This file only emits text commands; it
never accesses hardware.
"""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path


WARNING_SRK = """# These are One-Time Programmable e-fuses. Once you write them you can't
# go back, so get it right the first time!"""

WARNING_CLOSE = """# After the device successfully boots a signed image without generating
# any HAB events, it is safe to secure, or 'close', the device. This is
# the last step in the process. Once the fuse is blown, the chip does
# not load an image that has not been signed using the correct PKI tree.
# Be careful! This is again a One-Time Programmable e-fuse. Once you
# write it, you cannot go back. If anything in the previous steps was
# not done correctly, after writing this bit the device may not boot!"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--srk-fuse", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--srk-bank-start", required=True, type=int)
    parser.add_argument("--srk-word-start", required=True, type=int)
    parser.add_argument("--srk-word-count", required=True, type=int)
    parser.add_argument("--srk-words-per-bank", required=True, type=int)
    parser.add_argument("--close-bank", required=True, type=int)
    parser.add_argument("--close-word", required=True, type=int)
    parser.add_argument("--close-value", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.srk_word_count <= 0:
        print("ERROR: SRK word count must be positive", file=sys.stderr)
        return 2
    if args.srk_words_per_bank <= 0:
        print("ERROR: SRK words per bank must be positive", file=sys.stderr)
        return 2

    try:
        data = args.srk_fuse.read_bytes()
    except OSError as exc:
        print(f"ERROR: cannot read SRK fuse file {args.srk_fuse}: {exc}", file=sys.stderr)
        return 1

    expected_size = args.srk_word_count * 4
    if len(data) != expected_size:
        print(
            f"ERROR: SRK fuse file must be {expected_size} bytes "
            f"({args.srk_word_count} uint32 words), got {len(data)}",
            file=sys.stderr,
        )
        return 1

    try:
        close_value = int(args.close_value, 0)
    except ValueError:
        print(f"ERROR: invalid close fuse value: {args.close_value}", file=sys.stderr)
        return 2

    words = struct.unpack(f"<{args.srk_word_count}I", data)
    lines = [WARNING_SRK, "", "# i.MX8MP HABv4 SRK hash fuses"]
    for offset, word in enumerate(words):
        bank_offset, word_offset = divmod(offset, args.srk_words_per_bank)
        lines.append(
            f"fuse prog -y {args.srk_bank_start + bank_offset} "
            f"{args.srk_word_start + word_offset} 0x{word:08X}"
        )

    lines.extend(
        [
            "",
            WARNING_CLOSE,
            f"# Close SEC_CONFIG: bank {args.close_bank}, word {args.close_word}",
            f"fuse prog -y {args.close_bank} {args.close_word} 0x{close_value:08X}",
            "",
        ]
    )

    try:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text("\n".join(lines), encoding="utf-8")
    except OSError as exc:
        print(f"ERROR: cannot write fuse command file {args.output}: {exc}", file=sys.stderr)
        return 1

    print(f"Generated: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
