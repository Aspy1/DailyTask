import json

from scripts.hermes_plugin.documents import DocumentTools


def test_document_create_read_and_update(tmp_path) -> None:
    root = tmp_path / "documents"
    root.mkdir()
    tool = DocumentTools(root)

    def call(operation: str, **fields: str) -> dict:
        return json.loads(tool.call({"operation": operation, **fields}))

    created = call("write", path="notes.md", text="first", revision="new")
    assert created["ok"]
    assert call("read", path="notes.md")["text"] == "first"
    assert call("list")["entries"] == ["notes.md"]
    assert not call("write", path="notes.md", text="stale", revision="new")["ok"]
    assert call("write", path="notes.md", text="second", revision=created["revision"])["ok"]
    assert call("read", path="notes.md")["text"] == "second"


def test_files_outside_allowlist_are_not_accessible(tmp_path) -> None:
    root = tmp_path / "documents"
    root.mkdir()
    (root / "code.py").write_text("value = 1", encoding="utf-8")
    (tmp_path / "outside.txt").write_text("private", encoding="utf-8")
    tool = DocumentTools(root)
    for path in ("code.py", "../outside.txt", "/outside.txt",
                 str(tmp_path / "outside.txt"), "notes.md:stream"):
        assert not json.loads(tool.call({"operation": "read", "path": path}))["ok"]


def test_copy_binary_document_preserves_bytes_and_existing_destination(tmp_path) -> None:
    payload = b"%PDF-synthetic"
    (tmp_path / "original.pdf").write_bytes(payload)
    tool = DocumentTools(tmp_path)
    request = {"operation": "copy", "source": "original.pdf", "path": "copy.pdf"}
    assert json.loads(tool.call(request))["ok"]
    assert (tmp_path / "copy.pdf").read_bytes() == payload
    assert not json.loads(tool.call(request))["ok"]
    assert (tmp_path / "original.pdf").read_bytes() == payload
