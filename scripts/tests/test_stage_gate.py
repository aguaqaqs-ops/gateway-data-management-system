"""Narrow orchestration tests; run only on an occupied dedicated test node.

Substitute runner executables exercise exit/log/manifest semantics without Dolt,
Docker or deliberately damaging shared resources.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import signal
import tempfile
import threading
import types
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("stage_gate", Path(__file__).parents[1] / "run-stage-gate.py")
assert SPEC and SPEC.loader
G = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(G)
SHA = "a" * 40
OTHER = "b" * 40


def manifest(package, head=SHA, digest="same"):
    return {"package": package, "head": head, "worktree_head": head,
            "clean_worktree": True, "total_digest": digest}


class FakeClosureError(Exception):
    pass


class FixtureGate(G.Gate):
    """Replace only node/platform preparation; run real child executables."""
    def __init__(self, root, *, head=SHA, fresh=False, packages=None, digest="same", failure=0, sleep=False):
        args = argparse.Namespace(commit_sha=head, packages=packages or ["shared_kernel"], fresh=fresh,
                                  purpose="stage", session="selftest")
        super().__init__(args, "tool-v1")
        self.worktree = root / "worktree"
        self.results = root / "results"
        self.busy = root / "busy"
        self.tmp = root / "tmp"
        self.directory = self.results / head / self.run_id
        self.result["worktree"] = str(self.worktree)
        self.failure = failure
        self.sleep = sleep
        self.digest = digest
        self.site_calls = 0
        self.closure = types.SimpleNamespace(ClosureError=FakeClosureError,
            compare_manifests=lambda a, b: {"status": "可沿用" if a["total_digest"] == b["total_digest"] else "运行"})

    def load_config(self):
        self.result["cache_provenance"] = {"source": "selftest"}

    def site_clear(self):
        self.site_calls += 1

    def checkout(self):
        self.worktree.mkdir(exist_ok=True)
        self.result.update(start_head=self.args.commit_sha, clean_start=True)

    def prepare(self):
        self.tmp.mkdir(exist_ok=True)
        self.temporary_prepared = True
        path = self.worktree / "vnext/scripts"
        path.mkdir(parents=True, exist_ok=True)
        code = ["#!/usr/bin/env python3", "import json, os, time"]
        if self.sleep:
            code += ["time.sleep(30)"]
        for name in self.args.packages:
            code += [f"print('==> test input manifest package={name}', flush=True)",
                     f"print({json.dumps(json.dumps(manifest(name, self.args.commit_sha, self.digest)))}, flush=True)",
                     f"print('==> {name} status={'failed' if self.failure else 'passed'}', flush=True)"]
        code += [f"raise SystemExit({self.failure})"]
        runner = path / "run-tests.sh"
        runner.write_text("\n".join(code) + "\n")
        runner.chmod(0o755)

    def manifest(self, name):
        return manifest(name, self.args.commit_sha, self.digest)

    def git(self, *args, repo=None):
        if args == ("rev-parse", "HEAD"):
            return self.args.commit_sha
        if args[0] == "status":
            return ""
        if args[0] == "merge-base":
            return ""
        if args[0] == "log":
            return getattr(self, "changed", "")
        raise AssertionError(args)


class StageGateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def record(self, gate):
        return json.loads((gate.directory / "result.json").read_text())

    def test_invalid_inputs_reject_and_final_purposes_force_six_packages(self):
        for value in ("bad", "shared_kernel,shared_kernel", "", "backend,"):
            with self.subTest(value=value), self.assertRaises(argparse.ArgumentTypeError):
                G.parse_packages(value)
        with self.assertRaises(SystemExit):
            G.arguments(["main"])
        for purpose in ("s5", "release", "production"):
            parsed = G.arguments([SHA, "--purpose", purpose, "--packages", "shared_kernel"])
            self.assertTrue(parsed.fresh)
            self.assertEqual(parsed.packages, list(G.PACKAGES))
        self.assertEqual(G.arguments([SHA, "--fresh", "--packages", "backend"]).packages, list(G.PACKAGES))

    def test_occupied_node_is_never_adopted_or_deleted(self):
        busy = self.root / "busy"
        busy.mkdir()
        owner = busy / "owner.json"
        owner.write_text('{"run_id":"other"}')
        gate = FixtureGate(self.root)
        self.assertEqual(gate.run(), 3)
        self.assertEqual(owner.read_text(), '{"run_id":"other"}')
        self.assertEqual(gate.site_calls, 0)
        self.assertFalse(self.record(gate)["occupancy_released"])

    def test_success_logs_manifests_and_document_commit_carries_original_source(self):
        first = FixtureGate(self.root)
        self.assertEqual(first.run(), 0)
        record = self.record(first)
        self.assertEqual(record["packages"]["shared_kernel"]["mode"], "run")
        for reference in record["logs"].values():
            self.assertEqual(G.sha256(Path(reference["path"])), reference["sha256"])
        second = FixtureGate(self.root, head=OTHER)
        self.assertEqual(second.run(), 0)
        carried = self.record(second)["packages"]["shared_kernel"]
        self.assertEqual(carried["mode"], "carried")
        self.assertEqual(carried["source"]["commit_sha"], SHA)
        self.assertFalse((second.directory / "runner.log").exists())
        third = FixtureGate(self.root, head="c" * 40)
        self.assertEqual(third.run(), 0)
        self.assertEqual(self.record(third)["packages"]["shared_kernel"]["source"]["commit_sha"], SHA)

    def test_failed_runner_is_not_retried_or_reused_and_partial_success_not_eligible(self):
        first = FixtureGate(self.root, packages=["shared_kernel", "repository_contracts"], failure=7)
        self.assertEqual(first.run(), 7)
        record = self.record(first)
        self.assertEqual(record["runner_exit_code"], 7)
        self.assertEqual(record["status"], "failed")
        self.assertEqual(len(list(first.directory.glob("runner.log"))), 1)
        second = FixtureGate(self.root)
        self.assertEqual(second.run(), 0)
        self.assertEqual(self.record(second)["packages"]["shared_kernel"]["mode"], "run")

    def test_closure_change_fresh_and_corrupted_source_each_force_run(self):
        for change in ("closure", "fresh", "log", "manifest", "tool"):
            with self.subTest(change=change), tempfile.TemporaryDirectory(dir=self.root) as folder:
                root = Path(folder)
                first = FixtureGate(root)
                self.assertEqual(first.run(), 0)
                record = self.record(first)
                second = FixtureGate(root, head=OTHER, digest="changed" if change == "closure" else "same",
                                     fresh=change == "fresh")
                if change == "log":
                    Path(record["logs"]["runner"]["path"]).write_text("tampered")
                if change == "manifest":
                    Path(record["packages"]["shared_kernel"]["manifest"]["path"]).write_text("{}")
                if change == "tool":
                    second.tool_digest = "tool-v2"
                self.assertEqual(second.run(), 0)
                self.assertEqual(self.record(second)["packages"]["shared_kernel"]["mode"], "run")

    def test_signal_stops_child_and_records_failure_before_releasing_own_marker(self):
        gate = FixtureGate(self.root, sleep=True)
        timer = threading.Timer(0.3, lambda: os.kill(os.getpid(), signal.SIGTERM))
        timer.start()
        try:
            self.assertEqual(gate.run(), 143)
        finally:
            timer.cancel()
            timer.join()
        record = self.record(gate)
        self.assertEqual(record["status"], "failed")
        self.assertTrue(record["occupancy_released"])
        self.assertFalse(gate.busy.exists())

    def test_uncertain_cleanup_retains_marker_and_fails(self):
        gate = FixtureGate(self.root)
        gate.cleanup_uncertain = True
        self.assertNotEqual(gate.run(), 0)
        self.assertTrue(gate.busy.exists())
        self.assertFalse(self.record(gate)["occupancy_released"])

    def test_runtime_change_and_revert_or_image_label_change_prevents_container_carry(self):
        gate = FixtureGate(self.root, head=OTHER)
        image = {"labels": {"gateway.p2r1.build-input-revision": "input", "gateway.p2r1.source-tree-sha256": "tree"}}
        source = {"commit_sha": SHA, "container_gate": {"status": "run", "images": {"repository_service": image}}}
        with patch.object(gate, "repository_identity", return_value={"build_input_revision": "input", "source_tree_sha256": "tree"}), \
             patch.object(gate, "image", return_value=image):
            self.assertTrue(gate.container_equivalent(source, "backend")[0])
            gate.changed = "vnext/deploy/compose.yaml\nvnext/deploy/compose.yaml"
            self.assertFalse(gate.container_equivalent(source, "backend")[0])
            gate.changed = ""
            image["labels"]["gateway.p2r1.source-tree-sha256"] = "changed"
            self.assertFalse(gate.container_equivalent(source, "repository_service")[0])

    def test_runner_manifest_uses_actual_input_and_rejects_missing_or_duplicate_markers(self):
        gate = FixtureGate(self.root, digest="prepared")
        original = gate.prepare
        def prepare_changed_runner():
            original()
            runner = gate.worktree / "vnext/scripts/run-tests.sh"
            runner.write_text(runner.read_text().replace("prepared", "actual"))
        with patch.object(gate, "prepare", side_effect=prepare_changed_runner):
            self.assertEqual(gate.run(), 0)
        self.assertEqual(self.record(gate)["packages"]["shared_kernel"]["total_digest"], "actual")
        for raw in ("", "==> test input manifest package=shared_kernel\n{}\n" * 2):
            with self.assertRaises(G.GateError):
                G.runner_manifests(raw, ["shared_kernel"])


if __name__ == "__main__":
    unittest.main()
