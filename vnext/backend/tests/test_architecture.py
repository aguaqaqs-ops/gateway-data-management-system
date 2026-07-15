from pathlib import Path


def test_vnext_source_does_not_import_legacy_code() -> None:
    source_root = Path(__file__).parents[1] / "src"
    forbidden = ("import legacy", "from legacy", "import backend_vnext", "from backend_vnext")

    for source in source_root.rglob("*.py"):
        assert not any(marker in source.read_text() for marker in forbidden), source
