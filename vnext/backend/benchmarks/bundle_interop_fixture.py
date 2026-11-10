"""Generate the small shared FE PAX fixture with the production assembler/encoder."""

from __future__ import annotations

from gateway_backend.artifacts.location import ArtifactLocation, build_artifact_id

import argparse
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq  # type: ignore[import-untyped]

from gateway_backend.artifacts import put_with_built_ref
from gateway_backend.application.bundle_download import prepare_bundle_download
from gateway_backend.artifacts.tar_stream import TarMember, pax_record_chunks
from gateway_backend.capabilities.bundle_assembly import (
    BundleArtifactBinding, BundleArtifactClosure, BundleArtifactKind, BundlePairInput, assemble_bundle,
)
from gateway_backend.infrastructure.artifact_store import LocalArtifactStore, ArtifactStoreLayout
from tests.test_bundle_assembly import _request, _surface_result


def generate(output: Path) -> None:
    output.mkdir(parents=True, exist_ok=False)
    with tempfile.TemporaryDirectory(prefix="bundle-interop-source-") as temporary:
        roots = {location.value: Path(temporary) / location.value for location in ArtifactLocation}
        for path in roots.values():
            path.mkdir()
        store = LocalArtifactStore(ArtifactStoreLayout(**roots), staging_max_bytes=4 * 1024**3)
        paths = ("dir/" * 70 + "rows.parquet", "目录/" * 60 + "表.parquet", "😀/" * 60 + "表.parquet")
        bindings = []
        for index, path in enumerate(paths):
            sink = pa.BufferOutputStream()
            pq.write_table(pa.table({"id": [index], "label": [f"vector-{index}"]}), sink)
            ref = put_with_built_ref(store, sink.getvalue().to_pybytes(), artifact_id=build_artifact_id(ArtifactLocation.EXPORT, "bundle-interop-fixture", index), media_type="application/vnd.apache.parquet")
            bindings.append(BundleArtifactBinding(ref, "shared/" + path, BundleArtifactKind.OTHER, shared=True))
        result = assemble_bundle(_request((BundlePairInput("pair", 0, 1, _surface_result()),),
            shared=BundleArtifactClosure(tuple(bindings))), source_store=store)
        if result.bundle is None:
            raise RuntimeError("interop fixture assembly failed")
        prepared = prepare_bundle_download(store, result.bundle.manifest_ref.artifact_id)
        try:
            with (output / "bundle.tar").open("wb") as target:
                for chunk in prepared.stream:
                    target.write(chunk)
        finally:
            prepared.close()
        (output / "manifest.json").write_bytes(store.locate(result.bundle.manifest_ref))
        (output / "artifact-closure.json").write_bytes(store.locate(result.bundle.artifact_closure_ref))
        records = {
            "literal_utf8": b"".join(pax_record_chunks("path", "中")).hex(),
            "adjacent_records": (b"".join(pax_record_chunks("path", "中")) + b"".join(pax_record_chunks("comment", "😀"))).hex(),
            "prefix_99": b"".join(pax_record_chunks("path", "a" * 90)).hex(),
            "prefix_101": b"".join(pax_record_chunks("path", "a" * 91)).hex(),
            "invalid_wrong_byte_length": "10 path=中\n".encode().hex(),
            "invalid_no_newline": "11 path=中".encode().hex(),
            "invalid_truncated_utf8": b"11 path=\xe4\xb8\n".hex(),
        }
        (output / "pax-records.json").write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n")
        sizes = []
        for size in (8**11 - 1, 8**11, 2**53 - 1):
            header = b"".join(TarMember("rows.parquet", size).prefix())
            name = f"size-{size}-header-only.bin"
            (output / name).write_bytes(header)
            sizes.append({"size_bytes": size, "header_only_file": name, "header_length": len(header),
                          "complete_tar": False, "framed_size": TarMember("rows.parquet", size).framed_size})
        (output / "size-vectors.json").write_text(json.dumps(sizes, indent=2) + "\n")
        command = ["git", "rev-parse", "HEAD"]
        candidate = subprocess.run(command, check=True, capture_output=True, text=True).stdout.strip()
        files = [{"path": path.name, "length": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                 for path in sorted(output.iterdir())]
        artifact_entries = [{"logical_path": entry["logical_path"], "size_bytes": entry["size_bytes"], "raw_sha256": entry["raw_sha256"]}
                            for entry in json.loads((output / "artifact-closure.json").read_bytes())["closure_entries"]]
        report = {"candidate": candidate, "production_encoder": "gateway_backend.artifacts.tar_stream",
                  "bundle_digest": prepared.bundle_digest, "content_length": prepared.content_length,
                  "files": files, "ordinary_artifacts": artifact_entries,
                  "frontend_interop_status": "pending; this exact bundle.tar must be used for parsing/hash/OPFS"}
        (output / "index.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    generate(parser.parse_args().output)
