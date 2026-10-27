"""Immutable, checksummed Skill/Memory bundles on a local filesystem."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import uuid

from .store import encode


def checksum(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def fsync_directory(path):
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write_text(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    with temporary.open("w", encoding="utf-8") as f:
        f.write(content)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temporary, path)
    fsync_directory(path.parent)


def write_json(path, value):
    write_text(path, encode(value))


def snapshot_sqlite(source, target):
    """SQLite backup includes committed WAL content; copying just the DB file does not."""
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(Path(source).resolve().as_uri() + "?mode=ro", uri=True)
    dst = sqlite3.connect(target)
    try:
        src.backup(dst)
        dst.execute("PRAGMA journal_mode=DELETE")
        if dst.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise ValueError("Invalid SQLite snapshot")
    finally:
        dst.close()
        src.close()
    with target.open("rb") as f:
        os.fsync(f.fileno())
    fsync_directory(target.parent)


class Releases:
    def __init__(self, root):
        self.root = Path(root).resolve()

    def build(self, skill, memory, *, profile, parent_revision, metadata=None):
        release_id = uuid.uuid4().hex
        base = self.root / "releases"
        base.mkdir(parents=True, exist_ok=True)
        staged = base / (".staging-" + release_id)
        staged.mkdir()
        shutil.copyfile(skill, staged / "SKILL.md")
        snapshot_sqlite(memory, staged / "memory.sqlite")
        manifest = {"id": release_id, "parent_revision": parent_revision,
                    "profile": profile, "metadata": metadata or {},
                    "files": {name: checksum(staged / name) for name in ("SKILL.md", "memory.sqlite")}}
        write_json(staged / "manifest.json", manifest)
        for file in staged.iterdir():
            with file.open("rb") as f:
                os.fsync(f.fileno())
            file.chmod(0o400)
        fsync_directory(staged)
        os.replace(staged, base / release_id)
        fsync_directory(base)
        return manifest

    def verify(self, manifest):
        release_id = manifest["id"]
        if len(release_id) != 32 or any(c not in "0123456789abcdef" for c in release_id):
            raise ValueError("Invalid release ID")
        path = self.root / "releases" / release_id
        if json.loads((path / "manifest.json").read_text()) != manifest:
            raise ValueError("Release manifest mismatch")
        for name in ("SKILL.md", "memory.sqlite"):
            if checksum(path / name) != manifest["files"][name]:
                raise ValueError("Release checksum mismatch")
        return path
