from __future__ import annotations

import struct
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import patch_ibox_250 as patcher


class BranchEncodingTests(unittest.TestCase):
    def test_forward_b(self) -> None:
        encoded = patcher.arm64_b(0x1000, 0x1010)
        self.assertEqual(struct.unpack("<I", encoded)[0], 0x14000004)

    def test_backward_bl(self) -> None:
        encoded = patcher.arm64_bl(0x1010, 0x1000)
        self.assertEqual(struct.unpack("<I", encoded)[0], 0x97FFFFFC)

    def test_unaligned_target_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "aligned"):
            patcher.arm64_b(0x1000, 0x1002)

    def test_out_of_range_target_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "range"):
            patcher.arm64_b(0, 1 << 29)


class SafetyTests(unittest.TestCase):
    def test_patch_count_is_stable(self) -> None:
        self.assertEqual(len(patcher.PATCHES), 82)

    def test_unknown_binary_is_rejected(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "version-unsafe"):
            patcher.patch_executable(b"not the analyzed binary")

    def test_all_patches_preserve_size(self) -> None:
        for patch in patcher.PATCHES:
            self.assertEqual(len(patch.expected), len(patch.replacement))


if __name__ == "__main__":
    unittest.main()

