#!/usr/bin/env python3
"""Version-bound ARM64 patcher for the analyzed iBox 2.5.0 IPA.

The tool suppresses selected presentation paths, redirects rewarded-ad gates
through the application's existing reward/close handlers, and makes a forced
update dismissible. The output IPA must be re-signed before installation.
"""

from __future__ import annotations

import argparse
import hashlib
import struct
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path


EXECUTABLE = "Payload/Player.app/Player"
EXPECTED_EXECUTABLE_SHA256 = (
    "22ffcd8a53ca28eceb4277cfbb8de0319c97c731e2a7ff9a2ae0ed5851719819"
)

RET = bytes.fromhex("c0035fd6")
NOP = bytes.fromhex("1f2003d5")
MOV_X0_X20 = bytes.fromhex("e00314aa")
MOV_X0_X19 = bytes.fromhex("e00313aa")

SWIFT_RETAIN = 0x026AE98C
SWIFT_RELEASE = 0x026AE980
SWIFT_BRIDGE_OBJECT_RELEASE = 0x026AF484


@dataclass(frozen=True)
class Patch:
    offset: int
    expected: bytes
    replacement: bytes
    description: str


def arm64_branch(source_offset: int, target_offset: int, *, link: bool) -> bytes:
    """Encode an ARM64 B or BL using file offsets in the same __TEXT mapping."""
    delta = target_offset - source_offset
    if delta % 4:
        raise ValueError("ARM64 branch target is not 4-byte aligned")
    imm26 = delta >> 2
    if not -(1 << 25) <= imm26 < (1 << 25):
        raise ValueError("ARM64 branch target is out of range")
    opcode = 0x94000000 if link else 0x14000000
    return struct.pack("<I", opcode | (imm26 & 0x03FFFFFF))


def arm64_b(source_offset: int, target_offset: int) -> bytes:
    return arm64_branch(source_offset, target_offset, link=False)


def arm64_bl(source_offset: int, target_offset: int) -> bytes:
    return arm64_branch(source_offset, target_offset, link=True)


REGULAR_AD_PATCHES = (
    Patch(
        0x00309840,
        bytes.fromhex("f44fbea9"),
        arm64_b(0x00309840, 0x0030BCB8),
        "skip splash through the application's normal close path",
    ),
    Patch(
        0x000A01D8,
        bytes.fromhex("f657bda9"),
        RET,
        "suppress profile-page banner attachment",
    ),
    Patch(
        0x000A0808,
        bytes.fromhex("f657bda9"),
        RET,
        "suppress profile-page native-ad attachment",
    ),
    Patch(
        0x0067947C,
        bytes.fromhex("f44fbea9"),
        RET,
        "suppress main-page interstitial presentation",
    ),
)


# name, didLoad, didReward, didClose, didFailToLoad, didLoad body
REWARDED_FLOWS = (
    ("DownloadItem", 0x0013B154, 0x0013B1A4, 0x0013B28C, 0x0013B2B4, 0x0013C348),
    ("ComicDetail", 0x0018A590, 0x0018A5E0, 0x0018A750, 0x0018A778, 0x0018A7AC),
    ("Video", 0x001E843C, 0x001E848C, 0x001E89A4, 0x001E89CC, 0x001E8A9C),
    ("AdRemoval", 0x0024C2B8, 0x0024C308, 0x0024CC04, 0x0024CC2C, 0x00251990),
    ("ReadAds", 0x002D30F8, 0x002D3148, 0x002D36EC, 0x002D3714, 0x002D3780),
    ("ComicPlay", 0x003D110C, 0x003D115C, 0x003D12C8, 0x003D12F0, 0x003D18AC),
    ("MusicAds", 0x0043B388, 0x0043B3D8, 0x0043B91C, 0x0043B944, 0x0043B9B0),
    ("ReadDetail", 0x00453970, 0x004539C0, 0x00453B30, 0x00453B58, 0x00453B8C),
    ("PanFolder", 0x00533418, 0x00533468, 0x00533554, 0x0053357C, 0x00533924),
    ("BookAds", 0x00589898, 0x005898E8, 0x00589F44, 0x00589F6C, 0x00589FD8),
    ("Player", 0x005EE98C, 0x005EE9DC, 0x005EEAA4, 0x005EEACC, 0x005EEBA8),
)


def rewarded_patches() -> tuple[Patch, ...]:
    patches: list[Patch] = []
    for name, loaded, rewarded, closed, failed, original_body in REWARDED_FLOWS:
        patches.extend(
            (
                Patch(
                    loaded + 0x2C,
                    arm64_bl(loaded + 0x2C, SWIFT_RETAIN),
                    NOP,
                    f"{name}: omit redundant didLoad self retain",
                ),
                Patch(
                    loaded + 0x34,
                    arm64_bl(loaded + 0x34, original_body),
                    arm64_bl(loaded + 0x34, rewarded),
                    f"{name}: invoke the existing reward-success handler",
                ),
                Patch(
                    loaded + 0x38,
                    MOV_X0_X20,
                    MOV_X0_X19,
                    f"{name}: select retained ad object for release",
                ),
                Patch(
                    loaded + 0x3C,
                    arm64_bl(loaded + 0x3C, SWIFT_RELEASE),
                    arm64_bl(loaded + 0x3C, SWIFT_BRIDGE_OBJECT_RELEASE),
                    f"{name}: preserve bridge-object release semantics",
                ),
                Patch(
                    loaded + 0x40,
                    MOV_X0_X19,
                    MOV_X0_X20,
                    f"{name}: pass the controller to the close handler",
                ),
                Patch(
                    loaded + 0x4C,
                    arm64_b(loaded + 0x4C, SWIFT_BRIDGE_OBJECT_RELEASE),
                    arm64_b(loaded + 0x4C, closed),
                    f"{name}: continue through the normal close path",
                ),
                Patch(
                    failed,
                    bytes.fromhex("f657bda9" if name == "Player" else "f44fbea9"),
                    arm64_b(failed, loaded),
                    f"{name}: route load failure through the unlock flow",
                ),
            )
        )
    return tuple(patches)


FORCED_UPDATE_PATCHES = (
    Patch(
        0x00C72D44,
        bytes.fromhex("08140037"),
        NOP,
        "treat forced updates as dismissible optional updates",
    ),
)

PATCHES = REGULAR_AD_PATCHES + rewarded_patches() + FORCED_UPDATE_PATCHES


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def patch_executable(data: bytes) -> tuple[bytes, list[str]]:
    actual_hash = sha256(data)
    if actual_hash != EXPECTED_EXECUTABLE_SHA256:
        raise RuntimeError(
            "unexpected Player binary; refusing version-unsafe patch: "
            f"expected {EXPECTED_EXECUTABLE_SHA256}, got {actual_hash}"
        )

    patched = bytearray(data)
    applied: list[str] = []
    for patch in PATCHES:
        end = patch.offset + len(patch.expected)
        current = bytes(patched[patch.offset:end])
        if current != patch.expected:
            raise RuntimeError(
                f"preimage mismatch at 0x{patch.offset:x}: "
                f"expected {patch.expected.hex()}, got {current.hex()}"
            )
        if len(patch.expected) != len(patch.replacement):
            raise RuntimeError(f"size-changing patch at 0x{patch.offset:x} is forbidden")
        patched[patch.offset:end] = patch.replacement
        applied.append(
            f"0x{patch.offset:08x}: {patch.expected.hex()} -> "
            f"{patch.replacement.hex()} ({patch.description})"
        )
    return bytes(patched), applied


def patch_ipa(source: Path, destination: Path) -> tuple[str, str, list[str]]:
    if source.resolve() == destination.resolve():
        raise RuntimeError("source and destination must be different files")
    if destination.exists():
        raise RuntimeError(f"destination already exists: {destination}")

    with zipfile.ZipFile(source, "r") as zin:
        if EXECUTABLE not in set(zin.namelist()):
            raise RuntimeError(f"missing {EXECUTABLE} in IPA")
        patched_executable, applied = patch_executable(zin.read(EXECUTABLE))

        with zipfile.ZipFile(destination, "w", allowZip64=True) as zout:
            for item in zin.infolist():
                payload = (
                    patched_executable
                    if item.filename == EXECUTABLE
                    else zin.read(item.filename)
                )
                zout.writestr(item, payload)

    return sha256(source.read_bytes()), sha256(destination.read_bytes()), applied


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="original iBox 2.5.0 IPA")
    parser.add_argument("destination", type=Path, help="new output IPA")
    args = parser.parse_args()

    try:
        source_hash, destination_hash, applied = patch_ipa(
            args.source.resolve(), args.destination.resolve()
        )
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"source_sha256={source_hash}")
    print(f"patched_sha256={destination_hash}")
    print(f"output={args.destination.resolve()}")
    for line in applied:
        print(line)
    print("note=output IPA must be re-signed before installation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

