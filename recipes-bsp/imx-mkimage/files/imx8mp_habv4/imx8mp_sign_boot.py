#!/usr/bin/env python3
"""Sign the i.MX8MP SPL and second-loader/FIT regions in flash.bin."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys


HAB_IVT_WORD = 0x402000D1
HAB_IVT_MASK = 0xF0FFFFFF
NUMBER = r"(0x[0-9a-fA-F]+)"


def number(value):
    return int(value, 0)


def fail(message):
    raise RuntimeError(message)


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def unique_match(text, expression, description, groups):
    matches = re.findall(expression, text, re.MULTILINE | re.IGNORECASE)
    normalized = set()
    for match in matches:
        if groups == 1:
            match = (match,)
        normalized.add(tuple(int(value, 0) for value in match))
    if len(normalized) != 1:
        rendered = ", ".join(str(item) for item in sorted(normalized)) or "none"
        fail(f"expected one {description} in mkimage log, found: {rendered}")
    return next(iter(normalized))


def parse_mkimage_log(path):
    text = path.read_text(errors="strict")
    spl = unique_match(
        text,
        rf"^\s*spl hab block:\s*{NUMBER}\s+{NUMBER}\s+{NUMBER}\s*$",
        "SPL HAB block",
        3,
    )
    spl_csf, = unique_match(
        text, rf"^\s*csf_off\s+{NUMBER}\s*$", "SPL CSF offset", 1
    )
    sld = unique_match(
        text,
        rf"^\s*sld hab block:\s*{NUMBER}\s+{NUMBER}\s+{NUMBER}\s*$",
        "second-loader HAB block",
        3,
    )
    sld_csf, = unique_match(
        text,
        rf"^\s*sld_csf_off\s+{NUMBER}\s*$",
        "second-loader CSF offset",
        1,
    )
    fit_fdt_csf, = unique_match(
        text,
        rf"^\s*fit-fdt csf_off\s+{NUMBER}\s*$",
        "FIT-FDT CSF offset",
        1,
    )
    return spl, spl_csf, sld, sld_csf, fit_fdt_csf


def parse_fit_log(path):
    blocks = []
    expression = re.compile(
        rf"^\s*{NUMBER}\s+{NUMBER}\s+{NUMBER}\s*$", re.MULTILINE
    )
    for match in expression.finditer(path.read_text(errors="strict")):
        blocks.append(tuple(int(value, 0) for value in match.groups()))
    if not blocks:
        fail(f"no FIT HAB blocks found in {path}")
    if len(set(blocks)) != len(blocks):
        fail(f"duplicate FIT HAB blocks found in {path}")
    return blocks


def ranges_overlap(start_a, size_a, start_b, size_b):
    return start_a < start_b + size_b and start_b < start_a + size_a


def validate_block(block, file_size, description):
    address, offset, size = block
    if size <= 0:
        fail(f"{description} has zero length")
    if offset < 0 or offset + size > file_size:
        fail(
            f"{description} range 0x{offset:x}+0x{size:x} exceeds "
            f"flash.bin size 0x{file_size:x}"
        )
    if address < 0 or address + size > 0x100000000:
        fail(f"{description} address range exceeds HABv4 32-bit space")


def read_ivt(image, offset, ivt_size, description):
    if offset < 0 or offset + ivt_size > len(image):
        fail(f"{description} IVT lies outside flash.bin")
    words = struct.unpack_from("<8I", image, offset)
    if words[0] & HAB_IVT_MASK != HAB_IVT_WORD:
        fail(
            f"{description} IVT has bad header 0x{words[0]:08x} at "
            f"file offset 0x{offset:x}"
        )
    if words[2] or words[3] or words[7]:
        fail(f"{description} IVT reserved/DCD fields are not zero")
    if words[5] == 0 or words[6] == 0:
        fail(f"{description} IVT self/CSF pointer is zero")
    return words


def write_csf(path, srk_table, csf_cert, img_cert, source_index, blocks):
    rendered_blocks = ", \\\n        ".join(
            f'0x{address:x} 0x{offset:x} 0x{size:x} "flash.bin"'
            for address, offset, size in blocks
        )
    path.write_text(
        f"""[Header]
    Version = 4.3
    Hash Algorithm = sha256
    Engine = CAAM
    Engine Configuration = 0
    Certificate Format = X509
    Signature Format = CMS

[Install SRK]
    File = \"{srk_table}\"
    Source index = {source_index}

[Install CSFK]
    File = \"{csf_cert}\"

[Authenticate CSF]

[Unlock]
    Engine = CAAM
    Features = MID

[Install Key]
    Verification index = 0
    Target index = 2
    File = \"{img_cert}\"

[Authenticate Data]
    Verification index = 2
    Blocks = {rendered_blocks}
"""
    )


def run_cst(cst, csf_text, csf_binary, workdir):
    result = subprocess.run(
        [str(cst), "--o", str(csf_binary), "--i", str(csf_text)],
        cwd=workdir,
        text=True,
    )
    if result.returncode:
        fail(f"CST failed for {csf_text.name} with exit code {result.returncode}")
    if not csf_binary.is_file():
        fail(f"CST did not generate {csf_binary}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--flash", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--workdir", required=True, type=Path)
    parser.add_argument("--mkimage-log", required=True, type=Path)
    parser.add_argument("--fit-log", required=True, type=Path)
    parser.add_argument("--cst", required=True, type=Path)
    parser.add_argument("--srk-table", required=True, type=Path)
    parser.add_argument("--csf-cert", required=True, type=Path)
    parser.add_argument("--img-cert", required=True, type=Path)
    parser.add_argument("--source-index", required=True, type=int)
    parser.add_argument("--ivt-size", required=True, type=number)
    parser.add_argument("--csf-max-size", required=True, type=number)
    args = parser.parse_args()

    args.flash = args.flash.resolve()
    args.output = args.output.absolute()
    args.workdir = args.workdir.absolute()
    args.mkimage_log = args.mkimage_log.resolve()
    args.fit_log = args.fit_log.resolve()
    args.cst = args.cst.resolve()
    args.srk_table = args.srk_table.resolve()
    args.csf_cert = args.csf_cert.resolve()
    args.img_cert = args.img_cert.resolve()

    if args.ivt_size != 0x20:
        fail(f"unsupported HAB IVT size: 0x{args.ivt_size:x}")
    for path, description in (
        (args.flash, "flash.bin"),
        (args.mkimage_log, "mkimage log"),
        (args.fit_log, "print_fit_hab log"),
        (args.cst, "CST binary"),
        (args.srk_table, "SRK table"),
        (args.csf_cert, "CSF certificate"),
        (args.img_cert, "IMG certificate"),
    ):
        if not path.is_file():
            fail(f"{description} not found: {path}")
    if not os.access(args.cst, os.X_OK):
        fail(f"CST binary is not executable: {args.cst}")

    args.workdir.mkdir(parents=True, exist_ok=True)
    (spl_block, spl_csf_offset, sld_block, sld_csf_offset,
     fit_fdt_csf_offset) = parse_mkimage_log(args.mkimage_log)
    fit_blocks = parse_fit_log(args.fit_log)
    flash_data = bytearray(args.flash.read_bytes())
    file_size = len(flash_data)

    validate_block(spl_block, file_size, "SPL HAB block")
    validate_block(sld_block, file_size, "second-loader HAB block")
    for index, block in enumerate(fit_blocks):
        validate_block(block, file_size, f"FIT HAB block {index}")

    if spl_block[1] + spl_block[2] != spl_csf_offset:
        fail("SPL HAB block end does not equal SPL CSF offset")
    if sld_block[1] + sld_block[2] != sld_csf_offset:
        fail("second-loader HAB block end does not equal its CSF offset")
    # imx-mkimage places an optional FIT-FDT IVT before the full configured
    # CSF_SIZE has elapsed.  Derive the actual second-loader CSF slot from the
    # reported FIT-FDT CSF pointer instead of assuming a fixed 0x2000 bytes.
    fit_fdt_ivt_offset = fit_fdt_csf_offset - args.ivt_size
    fit_csf_slot_size = fit_fdt_ivt_offset - sld_csf_offset
    if fit_csf_slot_size <= 0 or fit_csf_slot_size > args.csf_max_size:
        fail(
            f"invalid dynamic FIT CSF slot size 0x{fit_csf_slot_size:x}"
        )
    csf_slots = (
        ("SPL", spl_csf_offset, args.csf_max_size),
        ("FIT", sld_csf_offset, fit_csf_slot_size),
    )
    for name, offset, slot_size in csf_slots:
        if offset < 0 or offset + slot_size > file_size:
            fail(f"{name} CSF reservation lies outside flash.bin")
        if any(flash_data[offset:offset + slot_size]):
            fail(f"{name} CSF reservation is not empty before signing")
    if ranges_overlap(
        spl_csf_offset, args.csf_max_size,
        sld_csf_offset, fit_csf_slot_size,
    ):
        fail("SPL and FIT CSF reservations overlap")
    for index, (_, offset, size) in enumerate(fit_blocks):
        for name, csf_offset, slot_size in csf_slots:
            if ranges_overlap(offset, size, csf_offset, slot_size):
                fail(f"FIT HAB block {index} overlaps the {name} CSF slot")

    spl_ivt = read_ivt(flash_data, spl_block[1], args.ivt_size, "SPL")
    if spl_ivt[5] != spl_block[0]:
        fail("SPL IVT self pointer does not match the mkimage HAB address")
    expected_spl_csf = spl_block[1] + spl_ivt[6] - spl_ivt[5]
    if expected_spl_csf != spl_csf_offset:
        fail("SPL IVT CSF pointer does not match the mkimage CSF offset")

    sld_ivt_offset = sld_csf_offset - args.ivt_size
    sld_ivt = read_ivt(flash_data, sld_ivt_offset, args.ivt_size, "FIT")
    expected_sld_self = sld_block[0] + sld_ivt_offset - sld_block[1]
    if sld_ivt[5] != expected_sld_self:
        fail("FIT IVT self pointer does not match the second-loader mapping")
    expected_sld_csf = sld_block[1] + sld_ivt[6] - sld_block[0]
    if expected_sld_csf != sld_csf_offset:
        fail("FIT IVT CSF pointer does not match the mkimage CSF offset")

    working_flash = args.workdir / "flash.bin"
    working_flash.write_bytes(flash_data)
    spl_csf_text = args.workdir / "csf_spl.txt"
    fit_csf_text = args.workdir / "csf_fit.txt"
    spl_csf_binary = args.workdir / "csf_spl.bin"
    fit_csf_binary = args.workdir / "csf_fit.bin"

    write_csf(
        spl_csf_text, args.srk_table, args.csf_cert, args.img_cert,
        args.source_index, [spl_block],
    )
    write_csf(
        fit_csf_text, args.srk_table, args.csf_cert, args.img_cert,
        args.source_index, [sld_block] + fit_blocks,
    )
    run_cst(args.cst, spl_csf_text, spl_csf_binary, args.workdir)
    run_cst(args.cst, fit_csf_text, fit_csf_binary, args.workdir)

    spl_csf = spl_csf_binary.read_bytes()
    fit_csf = fit_csf_binary.read_bytes()
    for name, data, slot_size in (
        ("SPL", spl_csf, args.csf_max_size),
        ("FIT", fit_csf, fit_csf_slot_size),
    ):
        if not data or len(data) > slot_size:
            fail(
                f"{name} CSF size 0x{len(data):x} is outside the reserved "
                f"0x{slot_size:x}-byte area"
            )

    flash_data[spl_csf_offset:spl_csf_offset + len(spl_csf)] = spl_csf
    flash_data[sld_csf_offset:sld_csf_offset + len(fit_csf)] = fit_csf
    if len(flash_data) != file_size:
        fail("inserting CSFs changed the flash.bin size")

    temporary_output = args.workdir / "flash.signed.tmp"
    temporary_output.write_bytes(flash_data)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    os.replace(temporary_output, args.output)
    if args.output.stat().st_size != file_size:
        fail("signed flash.bin final size check failed")

    def block_report(block):
        return {
            "address": f"0x{block[0]:x}",
            "offset": f"0x{block[1]:x}",
            "size": f"0x{block[2]:x}",
        }

    report = {
        "flash_size": f"0x{file_size:x}",
        "spl_block": block_report(spl_block),
        "spl_csf_offset": f"0x{spl_csf_offset:x}",
        "spl_csf_slot_size": f"0x{args.csf_max_size:x}",
        "spl_csf_size": f"0x{len(spl_csf):x}",
        "second_loader_block": block_report(sld_block),
        "second_loader_csf_offset": f"0x{sld_csf_offset:x}",
        "second_loader_csf_slot_size": f"0x{fit_csf_slot_size:x}",
        "second_loader_csf_size": f"0x{len(fit_csf):x}",
        "fit_blocks": [block_report(block) for block in fit_blocks],
        "unsigned_sha256": sha256(args.flash),
        "signed_sha256": sha256(args.output),
        "mkimage_log": str(args.mkimage_log),
        "print_fit_hab_log": str(args.fit_log),
    }
    (args.workdir / "imx-boot.hab.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n"
    )
    print(
        "i.MX8MP HAB boot: "
        f"size=0x{file_size:x} spl_csf=0x{spl_csf_offset:x} "
        f"fit_csf=0x{sld_csf_offset:x} fit_blocks={len(fit_blocks)}"
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)
