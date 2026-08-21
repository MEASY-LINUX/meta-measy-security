#!/usr/bin/env python3
"""Sign an ARM64 Linux Image with a HABv4 IVT and CSF.

All layout values are derived from the exact build artifacts.  The kernel
load address comes from the deployed U-Boot initial environment, and the IVT
offset comes from the ARM64 Image header rather than the file length.
"""

import argparse
import glob
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys


ARM64_MAGIC_OFFSET = 0x38
ARM64_MAGIC = b"ARM\x64"
ARM64_IMAGE_SIZE_OFFSET = 0x10
HAB_IVT_WORD = 0x412000D1


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


def parse_uboot_environment(deploy_dir, machine):
    pattern = str(deploy_dir / f"u-boot-imx-initial-env-{machine}-*")
    candidates = []
    seen = set()
    for name in sorted(glob.glob(pattern)):
        path = Path(name)
        try:
            resolved = path.resolve(strict=True)
        except FileNotFoundError:
            continue
        if resolved in seen or not resolved.is_file():
            continue
        seen.add(resolved)

        values = {}
        for line in resolved.read_text(errors="strict").splitlines():
            if "=" not in line or line.lstrip().startswith("#"):
                continue
            key, value = line.split("=", 1)
            if key in ("kernel_addr_r", "loadaddr"):
                try:
                    values[key] = int(value.strip(), 0)
                except ValueError:
                    fail(f"invalid {key} in {resolved}: {value!r}")

        if "kernel_addr_r" in values and "loadaddr" in values:
            if values["kernel_addr_r"] != values["loadaddr"]:
                fail(
                    f"U-Boot environment {resolved} has different kernel_addr_r "
                    f"(0x{values['kernel_addr_r']:x}) and loadaddr "
                    f"(0x{values['loadaddr']:x})"
                )
            candidates.append((resolved, values["kernel_addr_r"]))

    if not candidates:
        fail(f"no usable U-Boot initial environment matched {pattern}")

    addresses = {address for _, address in candidates}
    if len(addresses) != 1:
        details = ", ".join(f"{path}=0x{addr:x}" for path, addr in candidates)
        fail(f"ambiguous kernel load addresses: {details}")

    return candidates[0][1], [str(path) for path, _ in candidates]


def copy_with_fill(source, destination, final_size, fill=0x5A):
    with source.open("rb") as src, destination.open("wb") as dst:
        shutil.copyfileobj(src, dst, 1024 * 1024)
        remaining = final_size - dst.tell()
        if remaining < 0:
            fail(
                f"cannot pad {source}: size 0x{source.stat().st_size:x} exceeds "
                f"target 0x{final_size:x}"
            )
        block = bytes([fill]) * (1024 * 1024)
        while remaining:
            length = min(remaining, len(block))
            dst.write(block[:length])
            remaining -= length


def write_csf(path, srk_table, csf_cert, img_cert, source_index,
              load_address, auth_size, block_name):
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
    Blocks = 0x{load_address:x} 0x0 0x{auth_size:x} \"{block_name}\"
"""
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--workdir", required=True, type=Path)
    parser.add_argument("--deploy-dir", required=True, type=Path)
    parser.add_argument("--machine", required=True)
    parser.add_argument("--cst", required=True, type=Path)
    parser.add_argument("--srk-table", required=True, type=Path)
    parser.add_argument("--csf-cert", required=True, type=Path)
    parser.add_argument("--img-cert", required=True, type=Path)
    parser.add_argument("--source-index", required=True, type=int)
    parser.add_argument("--ivt-size", required=True, type=number)
    parser.add_argument("--csf-max-size", required=True, type=number)
    parser.add_argument("--align", required=True, type=number)
    args = parser.parse_args()

    # CST is executed with the signing work directory as cwd because Blocks
    # names the local Image_pad_ivt.bin.  Resolve every external input first
    # so relative command-line paths cannot silently change meaning.
    args.image = args.image.resolve()
    args.output = args.output.absolute()
    args.workdir = args.workdir.absolute()
    args.deploy_dir = args.deploy_dir.resolve()
    args.cst = args.cst.resolve()
    args.srk_table = args.srk_table.resolve()
    args.csf_cert = args.csf_cert.resolve()
    args.img_cert = args.img_cert.resolve()

    if args.ivt_size != 0x20:
        fail(f"unsupported HAB IVT size: 0x{args.ivt_size:x}")
    if args.align <= 0 or args.align & (args.align - 1):
        fail(f"Image alignment is not a power of two: 0x{args.align:x}")

    for path, description in (
        (args.image, "ARM64 Image"),
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
    load_address, env_sources = parse_uboot_environment(
        args.deploy_dir, args.machine
    )

    with args.image.open("rb") as stream:
        header = stream.read(ARM64_MAGIC_OFFSET + len(ARM64_MAGIC))
    if len(header) < ARM64_MAGIC_OFFSET + len(ARM64_MAGIC):
        fail(f"Image header is truncated: {args.image}")
    if header[ARM64_MAGIC_OFFSET:ARM64_MAGIC_OFFSET + 4] != ARM64_MAGIC:
        fail(f"invalid ARM64 Image magic at offset 0x{ARM64_MAGIC_OFFSET:x}")

    image_size = struct.unpack_from("<Q", header, ARM64_IMAGE_SIZE_OFFSET)[0]
    if image_size == 0:
        fail("ARM64 Image header image_size is zero")
    ivt_offset = (image_size + args.align - 1) & ~(args.align - 1)
    actual_size = args.image.stat().st_size
    if actual_size > ivt_offset:
        fail(
            f"Image file size 0x{actual_size:x} exceeds calculated IVT "
            f"offset 0x{ivt_offset:x}"
        )

    ivt_self = load_address + ivt_offset
    csf_address = ivt_self + args.ivt_size
    auth_size = ivt_offset + args.ivt_size
    final_size = auth_size + args.csf_max_size
    if max(ivt_self, csf_address) > 0xFFFFFFFF:
        fail("HABv4 IVT address exceeds the 32-bit address space")

    padded = args.workdir / "Image_pad.bin"
    ivt = args.workdir / "Image.ivt"
    pad_ivt = args.workdir / "Image_pad_ivt.bin"
    csf_text = args.workdir / "Image.csf"
    csf_binary = args.workdir / "Image_csf.bin"
    temporary_output = args.workdir / "Image.signed.tmp"

    copy_with_fill(args.image, padded, ivt_offset)
    ivt.write_bytes(
        struct.pack(
            "<8I",
            HAB_IVT_WORD,
            load_address,
            0,
            0,
            0,
            ivt_self,
            csf_address,
            0,
        )
    )
    if ivt.stat().st_size != args.ivt_size:
        fail(f"generated IVT has unexpected size: {ivt.stat().st_size}")

    with pad_ivt.open("wb") as dst, padded.open("rb") as src:
        shutil.copyfileobj(src, dst, 1024 * 1024)
        dst.write(ivt.read_bytes())
    if pad_ivt.stat().st_size != auth_size:
        fail("kernel plus IVT size does not match Authenticate Data length")

    write_csf(
        csf_text,
        args.srk_table,
        args.csf_cert,
        args.img_cert,
        args.source_index,
        load_address,
        auth_size,
        pad_ivt.name,
    )
    result = subprocess.run(
        [str(args.cst), "--o", str(csf_binary), "--i", str(csf_text)],
        cwd=args.workdir,
        text=True,
    )
    if result.returncode:
        fail(f"CST failed with exit code {result.returncode}")
    if not csf_binary.is_file():
        fail(f"CST did not generate {csf_binary}")
    csf_size = csf_binary.stat().st_size
    if csf_size == 0 or csf_size > args.csf_max_size:
        fail(
            f"CSF size 0x{csf_size:x} is outside the reserved "
            f"0x{args.csf_max_size:x}-byte area"
        )

    with temporary_output.open("wb") as dst, pad_ivt.open("rb") as src:
        shutil.copyfileobj(src, dst, 1024 * 1024)
        dst.write(csf_binary.read_bytes())
        remaining = final_size - dst.tell()
        if remaining < 0:
            fail("signed Image exceeds calculated final size")
        dst.write(bytes([0x5A]) * remaining)
    if temporary_output.stat().st_size != final_size:
        fail("final signed Image size check failed")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    os.replace(temporary_output, args.output)
    report = {
        "actual_size": f"0x{actual_size:x}",
        "arm64_image_size": f"0x{image_size:x}",
        "load_address": f"0x{load_address:x}",
        "ivt_offset": f"0x{ivt_offset:x}",
        "ivt_self": f"0x{ivt_self:x}",
        "csf_address": f"0x{csf_address:x}",
        "authenticate_data_size": f"0x{auth_size:x}",
        "csf_binary_size": f"0x{csf_size:x}",
        "final_size": f"0x{final_size:x}",
        "uboot_environment_sources": env_sources,
        "unsigned_sha256": sha256(args.image),
        "signed_sha256": sha256(args.output),
    }
    (args.workdir / "Image.hab.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n"
    )
    print(
        "i.MX8MP HAB Image: "
        f"load=0x{load_address:x} image_size=0x{image_size:x} "
        f"ivt=0x{ivt_offset:x} auth=0x{auth_size:x} "
        f"final=0x{final_size:x}"
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)
