#!/usr/bin/env python3
"""Unit tests for runtime_config_fixture kernel_threads overrides."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
VNEXT_ROOT = TESTS_DIR.parents[1]
FIXTURE_SCRIPT = TESTS_DIR / "runtime_config_fixture.py"
PRODUCTION_PROFILE = VNEXT_ROOT / "fixtures/runtime-config/v1/resource-profile.json"

sys.path.insert(0, str(TESTS_DIR))
import runtime_config_fixture  # noqa: E402


class RuntimeConfigFixtureTests(unittest.TestCase):
    def test_production_fixture_keeps_default_n1_profile(self) -> None:
        profile = json.loads(PRODUCTION_PROFILE.read_bytes())
        self.assertEqual(
            profile["worker"],
            {
                "count": 1,
                "active_limit": 1,
                "kernel_threads": 1,
                "kernel_memory_bytes": 25769803776,
                "memory_envelope_bytes": 34359738368,
                "memory_reserve_bytes": 8589934592,
                "cpu_limit": 2,
                "swap_limit_bytes": 0,
            },
        )

    def test_prepare_preserves_default_n1_when_kernel_threads_omitted(self) -> None:
        with tempfile.TemporaryDirectory(prefix="gdds-rt-fixture-") as tmp:
            directory = Path(tmp) / "fixture"
            override = runtime_config_fixture.prepare(directory)
            self.assertEqual(override, directory / "compose-runtime.json")
            profile = json.loads((directory / "resource-profile.json").read_bytes())
            self.assertEqual(profile["worker"]["kernel_threads"], 1)
            self.assertEqual(profile["worker"]["cpu_limit"], 2)
            self.assertEqual(profile["worker"]["kernel_memory_bytes"], 25769803776)
            self.assertEqual(profile["worker"]["memory_envelope_bytes"], 34359738368)
            self.assertEqual(profile["worker"]["memory_reserve_bytes"], 8589934592)

    def test_prepare_and_cli_apply_explicit_kernel_threads_without_changing_budgets(self) -> None:
        for threads in (1, 2):
            with self.subTest(threads=threads):
                with tempfile.TemporaryDirectory(prefix="gdds-rt-fixture-") as tmp:
                    directory = Path(tmp) / "fixture"
                    completed = subprocess.run(
                        [
                            sys.executable,
                            str(FIXTURE_SCRIPT),
                            str(directory),
                            "--workers",
                            "1",
                            "--kernel-threads",
                            str(threads),
                        ],
                        capture_output=True,
                        text=True,
                        check=False,
                        timeout=30,
                    )
                    self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
                    profile = json.loads((directory / "resource-profile.json").read_bytes())
                    self.assertEqual(profile["worker"]["count"], 1)
                    self.assertEqual(profile["worker"]["active_limit"], 1)
                    self.assertEqual(profile["worker"]["kernel_threads"], threads)
                    self.assertEqual(profile["worker"]["cpu_limit"], 2)
                    self.assertEqual(profile["worker"]["kernel_memory_bytes"], 25769803776)
                    self.assertEqual(profile["worker"]["memory_envelope_bytes"], 34359738368)
                    self.assertEqual(profile["worker"]["memory_reserve_bytes"], 8589934592)

    def test_prepare_and_cli_reject_invalid_kernel_threads(self) -> None:
        for bad_value in (0, -1, True, 3):
            with self.subTest(bad_value=bad_value):
                with tempfile.TemporaryDirectory(prefix="gdds-rt-fixture-") as tmp:
                    directory = Path(tmp) / "fixture"
                    with self.assertRaises(ValueError):
                        runtime_config_fixture.prepare(
                            directory, workers=1, kernel_threads=bad_value
                        )
                    self.assertFalse((directory / "resource-profile.json").exists())

        for cli_bad in ("0", "-1", "3"):
            with self.subTest(cli_bad=cli_bad):
                with tempfile.TemporaryDirectory(prefix="gdds-rt-fixture-") as tmp:
                    directory = Path(tmp) / "fixture"
                    completed = subprocess.run(
                        [
                            sys.executable,
                            str(FIXTURE_SCRIPT),
                            str(directory),
                            "--workers",
                            "1",
                            "--kernel-threads",
                            cli_bad,
                        ],
                        capture_output=True,
                        text=True,
                        check=False,
                        timeout=30,
                    )
                    self.assertNotEqual(completed.returncode, 0)
                    self.assertFalse((directory / "resource-profile.json").exists())


if __name__ == "__main__":
    unittest.main()
