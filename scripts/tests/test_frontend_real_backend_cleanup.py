"""Group-owner cleanup preserves failures and prevents releasing a busy node."""
from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class RealBackendCleanupExitTests(unittest.TestCase):
    def test_group_cleanup_failure_is_nonzero_and_preserves_main_failure(self) -> None:
        source = (ROOT / "frontend/scripts/run-real-backend-e2e.sh").read_text()
        cleanup = source[source.index("cleanup() {"):source.index("\non_signal() {")]
        for main_code, cleanup_code, expected in ((0, 42, 1), (7, 42, 7), (0, 0, 0)):
            with self.subTest(main_code=main_code, cleanup_code=cleanup_code), tempfile.TemporaryDirectory() as temporary:
                log = Path(temporary) / "cleanup.log"
                script = r'''
log() { printf '%s\n' "$*" >> "$LOG_FILE"; }
wait() { return "$INJECT_CLEANUP_CODE"; }
rewrite_marker_cleanup_failed() { return 0; }
TOOLCHAIN_CONTAINER=""; PROJECT_NAME=""; RS_TAG_SET=0; STACK_STARTED=0
GROUPS_PID=123; GROUPS_CONTROL="$CONTROL_DIR"; HAVE_FLOCK=0; HAVE_BUSY=0; INTERRUPT_SIGNAL=""; RUN_ROOT=""
'''
                (Path(temporary) / "groups-stopped.json").write_text("{}")
                script += cleanup
                script += '\n(exit "$INJECT_MAIN_CODE")\ncleanup\n'
                result = subprocess.run(["bash", "-c", script], capture_output=True, text=True, check=False,
                    env={"PATH": "/usr/bin:/bin", "REPO_DIR": str(ROOT), "LOG_FILE": str(log),
                         "CONTROL_DIR": temporary, "INJECT_MAIN_CODE": str(main_code), "INJECT_CLEANUP_CODE": str(cleanup_code)})
                self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
                text = log.read_text()
                self.assertIn(f"main_exit_code={main_code}\n", text)
                self.assertIn(f"exit_code={expected}\n", text)
                self.assertIn("cleanup_status=" + ("failed" if cleanup_code else "ok"), text)


if __name__ == "__main__":
    unittest.main()
