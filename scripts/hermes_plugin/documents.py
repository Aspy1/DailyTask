"""File tools for an operator-selected directory of non-code documents."""

import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from threading import Lock

MAX_BYTES = 512 * 1024
MAX_COPY_BYTES = 64 * 1024 * 1024
MAX_ENTRIES = 200
TEXT_SUFFIXES = frozenset({".txt", ".md", ".csv", ".tsv", ".json"})
DOCUMENT_SUFFIXES = TEXT_SUFFIXES | {".docx", ".xlsx", ".pptx", ".pdf", ".png", ".jpg", ".jpeg", ".webp"}
_FILE_LOCK = Lock()

SCHEMA = {
    "type": "object",
    "properties": {
        "operation": {"type": "string", "enum": ["list", "read", "write", "copy"]},
        "path": {"type": "string", "description": "Relative document path; omit for top-level listing."},
        "source": {"type": "string", "description": "Existing relative document path for a copy."},
        "text": {"type": "string", "description": "Complete UTF-8 text for a write."},
        "revision": {"type": "string", "description": "Revision returned by read, or 'new' to create."},
    },
    "required": ["operation"],
    "additionalProperties": False,
}


def _overlap(first: Path, second: Path) -> bool:
    return first.is_relative_to(second) or second.is_relative_to(first)


def _relative_path(value: object) -> Path:
    if not isinstance(value, str) or any(char in value for char in (":", "\\", "\x00")):
        raise ValueError("Use a relative path with forward slashes.")
    relative = Path(value)
    if relative.anchor or any(part.startswith(".") or part.endswith((" ", ".")) for part in relative.parts):
        raise ValueError("Hidden files and paths outside the document directory are unavailable.")
    return relative


class DocumentTools:
    def __init__(self, root: Path, protected: tuple[Path, ...] = ()) -> None:
        self.root = root.resolve()
        if not root.is_absolute() or not self.root.is_dir() or any(
                _overlap(self.root, path.resolve()) for path in protected):
            raise ValueError("Choose a dedicated existing document directory outside protected roots.")

    def call(self, arguments: object) -> str:
        try:
            result = self._dispatch(arguments)
        except (OSError, ValueError) as exc:
            error = str(exc) if isinstance(exc, ValueError) and not isinstance(exc, UnicodeError) else (
                "The document is unavailable or is not valid UTF-8.")
            result = {"ok": False, "error": error}
        return json.dumps(result, ensure_ascii=False)

    def _dispatch(self, arguments: object) -> dict:
        if not isinstance(arguments, dict):
            raise ValueError("Supply a structured document request.")
        operation = arguments.get("operation")
        keys = set(arguments) - {"operation", "path"}
        if operation == "list" and not keys:
            return self._list(self._target(arguments.get("path", ""), directory=True))
        path = arguments.get("path")
        if operation == "read" and not keys:
            text, revision = self._read(self._target(path))
            return {"ok": True, "text": text, "revision": revision}
        if operation == "write" and keys == {"text", "revision"}:
            return self._write(self._target(path), arguments["text"], arguments["revision"])
        if operation == "copy" and keys == {"source"}:
            source = self._target(arguments["source"], suffixes=DOCUMENT_SUFFIXES)
            destination = self._target(path, suffixes=DOCUMENT_SUFFIXES)
            return self._copy(source, destination)
        raise ValueError("Invalid document operation or arguments.")

    def _target(self, value: object, *, directory: bool = False,
                suffixes: frozenset[str] = TEXT_SUFFIXES) -> Path:
        target = self.root / _relative_path(value)
        self._check_location(target, directory=directory)
        if not directory and target.suffix.lower() not in suffixes:
            raise ValueError("This document format is unavailable for the requested operation.")
        if target.is_file() and target.stat().st_nlink != 1:
            raise ValueError("Linked files are unavailable.")
        return target

    def _check_location(self, target: Path, *, directory: bool) -> None:
        parents = (target, *target.parents) if directory else target.parents
        if not target.is_relative_to(self.root) or target.resolve() != target or any(
                (parent / ".git").exists() for parent in parents if parent.is_relative_to(self.root)):
            raise ValueError("Linked paths and Git workspaces are unavailable.")

    @staticmethod
    def _list(directory: Path) -> dict:
        entries = []
        for entry in directory.iterdir():
            if entry.name.startswith(".") or entry.resolve() != entry:
                continue
            if entry.is_dir() and not (entry / ".git").exists():
                entries.append(f"{entry.name}/")
            elif entry.is_file() and entry.suffix.lower() in DOCUMENT_SUFFIXES:
                entries.append(entry.name)
            if len(entries) == MAX_ENTRIES:
                return {"ok": True, "entries": sorted(entries), "truncated": True}
        return {"ok": True, "entries": sorted(entries), "truncated": False}

    @staticmethod
    def _read(target: Path) -> tuple[str, str]:
        with target.open("rb") as source:
            content = source.read(MAX_BYTES + 1)
        if len(content) > MAX_BYTES:
            raise ValueError("The document exceeds the text size limit.")
        return content.decode("utf-8"), hashlib.sha256(content).hexdigest()

    def _write(self, target: Path, text: object, revision: object) -> dict:
        if not isinstance(text, str) or not isinstance(revision, str):
            raise ValueError("Text and revision are required.")
        content = text.encode("utf-8")
        if len(content) > MAX_BYTES:
            raise ValueError("The document exceeds the text size limit.")
        with _FILE_LOCK:
            self._target(target.relative_to(self.root).as_posix())
            current = self._read(target)[1] if target.exists() else "new"
            if revision != current:
                raise ValueError("The document changed. Read it before updating.")
            self._commit(target, content, create=current == "new")
        return {"ok": True, "revision": hashlib.sha256(content).hexdigest()}

    @staticmethod
    def _copy(source: Path, destination: Path) -> dict:
        if source.suffix.lower() != destination.suffix.lower():
            raise ValueError("Keep the original file extension when copying a document.")
        if not source.is_file() or source.stat().st_size > MAX_COPY_BYTES:
            raise ValueError("The source must be a document of at most 64 MiB.")
        if destination.exists():
            raise ValueError("The destination already exists.")
        with source.open("rb") as original, tempfile.NamedTemporaryFile(
                dir=destination.parent, delete=False) as handle:
            pending = Path(handle.name)
            try:
                shutil.copyfileobj(original, handle)
                if handle.tell() > MAX_COPY_BYTES:
                    raise ValueError("The source exceeded the copy limit.")
                handle.close()
                os.link(pending, destination)
            finally:
                pending.unlink(missing_ok=True)
        return {"ok": True}

    @staticmethod
    def _commit(target: Path, content: bytes, *, create: bool) -> None:
        with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as handle:
            pending = Path(handle.name)
            try:
                handle.write(content)
                handle.close()
                if create:
                    os.link(pending, target)
                else:
                    os.replace(pending, target)
            finally:
                pending.unlink(missing_ok=True)
