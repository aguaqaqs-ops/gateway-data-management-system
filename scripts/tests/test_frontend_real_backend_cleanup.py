"""Group-owner cleanup preserves failures and prevents releasing a busy node."""
from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class RealBackendCleanupExitTests(unittest.TestCase):
    def test_group_cleanup_failure_is_nonzero_and_preserves_main_failure(self) -> None:
        source = (ROOT / "frontend/scripts/run-real-backend-e2e.sh").read_text()
        cleanup = source[source.index("cleanup() {"):source.index("\non_signal() {")]
        for main_code, cleanup_code, remove_failed, expected in ((0, 42, False, 1), (7, 42, False, 7), (0, 0, False, 0), (7, 0, False, 7), (143, 0, False, 143), (0, 0, True, 1)):
            with self.subTest(main_code=main_code, cleanup_code=cleanup_code), tempfile.TemporaryDirectory() as temporary:
                log = Path(temporary) / "cleanup.log"
                script = r'''
log() { printf '%s\n' "$*" >> "$LOG_FILE"; }
wait() { return "$INJECT_CLEANUP_CODE"; }
rewrite_marker_cleanup_failed() { return 0; }
cleanup_runtime_roots() { log "runtime_roots_delete_requested=true"; }
rm() {
  if [[ "$1" == "-rf" && "$INJECT_REMOVE_FAILURE" == "1" ]]; then return 41; fi
  command rm "$@"
}
TOOLCHAIN_CONTAINER=""; PROJECT_NAME=""; RS_TAG_SET=0; STACK_STARTED=0
GROUPS_PID=123; GROUPS_CONTROL="$CONTROL_DIR"; HAVE_FLOCK=0; HAVE_BUSY=1; INTERRUPT_SIGNAL="$INJECT_SIGNAL"; RUN_ROOT="$CONTROL_DIR/run"
mkdir "$RUN_ROOT"
BUSY_DIR="$CONTROL_DIR/busy"; SESSION=test
mkdir "$BUSY_DIR"
touch "$BUSY_DIR/$SESSION"
'''
                (Path(temporary) / "groups-stopped.json").write_text("{}")
                script += cleanup
                script += '\n(exit "$INJECT_MAIN_CODE")\ncleanup\n'
                result = subprocess.run(["bash", "-c", script], capture_output=True, text=True, check=False,
                    env={"PATH": "/usr/bin:/bin", "REPO_DIR": str(ROOT), "LOG_FILE": str(log),
                         "CONTROL_DIR": temporary, "INJECT_SIGNAL": "TERM" if main_code == 143 else "", "INJECT_REMOVE_FAILURE": str(int(remove_failed)), "INJECT_MAIN_CODE": str(main_code), "INJECT_CLEANUP_CODE": str(cleanup_code)})
                self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
                status = json.loads((Path(temporary) / "groups-run-status.json").read_text())
                self.assertEqual(status, {"main_exit_code": main_code, "cleanup_failed": False, "interrupted": main_code == 143})
                self.assertEqual((Path(temporary) / "busy").exists(), bool(cleanup_code or remove_failed))
                text = log.read_text()
                self.assertEqual("runtime_roots_delete_requested=true" in text, main_code == 0 and cleanup_code == 0 and not remove_failed)
                self.assertIn(f"main_exit_code={main_code}\n", text)
                self.assertIn(f"exit_code={expected}\n", text)
                self.assertIn("cleanup_status=" + ("failed" if cleanup_code or remove_failed else "ok"), text)


if __name__ == "__main__":
    unittest.main()
