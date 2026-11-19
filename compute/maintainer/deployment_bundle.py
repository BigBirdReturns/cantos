"""Streaming, data-only transport for retained deployment jobs.

Chunks bound each browser request; total limits still apply. Imported code is
never executed. Decision reproduction belongs to the installed job analyzer.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tempfile
import zipfile
import zlib

try:
    from .common import load, write, sha256_file
except ImportError:
    from common import load, write, sha256_file

MAX_BYTES = 1024 * 1024 * 1024
MAX_FILES = 100000
MAX_CHUNK = 4 * 1024 * 1024
MAX_MANIFEST = 32 * 1024 * 1024
RESERVED = re.compile(r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)", re.I)
HEX = re.compile(r"^[0-9a-f]{64}$")


def safe_name(name):
    if not isinstance(name, str) or not name or len(name) > 240 or "\\" in name or ":" in name:
        raise ValueError("Unsafe bundle path")
    path = PurePosixPath(name)
    if path.is_absolute() or path.as_posix() != name or any(
            p in (".", "..") or p.endswith((" ", ".")) or RESERVED.match(p)
            or any(ord(c) < 32 or c in '<>\"|?*' for c in p) for p in path.parts):
        raise ValueError("Unsafe bundle path: " + name)
    return name


def _entry(value, *, chunk=False):
    if not isinstance(value, dict) or set(value) != {"path", "sha256", "bytes"}:
        raise ValueError("Invalid bundle file record")
    safe_name(value["path"])
    if not isinstance(value["sha256"], str) or not HEX.fullmatch(value["sha256"]):
        raise ValueError("Invalid bundle digest")
    if type(value["bytes"]) is not int or not 0 <= value["bytes"] <= (MAX_CHUNK if chunk else MAX_BYTES):
        raise ValueError("Invalid bundle member size")


def validate_manifest(value):
    if not isinstance(value, dict) or set(value) != {
            "schema", "record", "files", "parts", "archive_sha256", "archive_bytes", "expanded_bytes"}:
        raise ValueError("Invalid deployment transport manifest")
    if value["schema"] != "cantos.deployment-bundle/1":
        raise ValueError("Unsupported deployment transport schema")
    safe_name(value["record"])
    files, parts = value["files"], value["parts"]
    if not isinstance(files, list) or not 1 <= len(files) <= MAX_FILES:
        raise ValueError("Bundle file count exceeds limit")
    if not isinstance(parts, list) or not 1 <= len(parts) <= MAX_BYTES // 65536 + 1:
        raise ValueError("Bundle part count exceeds limit")
    names = set()
    for entry in files:
        _entry(entry)
        key = entry["path"].casefold()
        if key in names:
            raise ValueError("Duplicate or case-colliding bundle path")
        names.add(key)
    for entry in files:
        if any(p.as_posix().casefold() in names for p in PurePosixPath(entry["path"]).parents):
            raise ValueError("Bundle file/directory collision")
    if value["record"] not in {e["path"] for e in files}:
        raise ValueError("Decision record missing from bundle")
    for index, entry in enumerate(parts):
        _entry(entry, chunk=True)
        if entry["path"] != f"part-{index:05d}.bin" or entry["bytes"] == 0:
            raise ValueError("Bundle parts must be complete and ordered")
    for field, expected in (("archive_bytes", sum(e["bytes"] for e in parts)),
                            ("expanded_bytes", sum(e["bytes"] for e in files))):
        if type(value[field]) is not int or value[field] != expected or not 0 < expected <= MAX_BYTES:
            raise ValueError("Bundle exceeds byte limit or declares inconsistent size")
    if not isinstance(value["archive_sha256"], str) or not HEX.fullmatch(value["archive_sha256"]):
        raise ValueError("Invalid archive digest")
    return value


def _files(root):
    records = []
    total = 0
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("Bundle source cannot contain symlinks")
        if path.is_dir():
            continue
        if not path.is_file():
            raise ValueError("Bundle source must contain regular files")
        name = safe_name(path.relative_to(root).as_posix())
        records.append({"path": name, "bytes": path.stat().st_size, "sha256": sha256_file(path)})
        total += records[-1]["bytes"]
        if len(records) > MAX_FILES or total > MAX_BYTES:
            raise ValueError("Bundle source exceeds transport limits")
    return records


def export_bundle(root, destination, *, record="decision.json", chunk_bytes=MAX_CHUNK):
    root, destination = Path(root).resolve(), Path(destination).resolve()
    if not root.is_dir() or destination == root or root in destination.parents:
        raise ValueError("Bundle destination must be outside the source directory")
    if type(chunk_bytes) is not int or not 65536 <= chunk_bytes <= MAX_CHUNK:
        raise ValueError("Chunk size must be 64 KiB to 4 MiB")
    files = _files(root)
    if safe_name(record) not in {entry["path"] for entry in files}:
        raise ValueError("Missing retained decision record")
    destination.mkdir(parents=True, exist_ok=False)
    with tempfile.TemporaryDirectory(prefix="cantos-deployment-export-") as scratch:
        archive_path = Path(scratch) / "evidence.zip"
        with zipfile.ZipFile(archive_path, "x", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
            for entry in files:
                source = root / entry["path"]
                archive.write(source, entry["path"])
                if source.stat().st_size != entry["bytes"] or sha256_file(source) != entry["sha256"]:
                    raise ValueError("Source changed during export")
        if archive_path.stat().st_size > MAX_BYTES:
            raise ValueError("Compressed archive exceeds transport limit")
        parts = []
        with archive_path.open("rb") as stream:
            while data := stream.read(chunk_bytes):
                name = f"part-{len(parts):05d}.bin"
                with (destination / name).open("xb") as output:
                    output.write(data)
                parts.append({"path": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
        manifest = {"schema": "cantos.deployment-bundle/1", "record": record,
                    "files": files, "parts": parts,
                    "archive_sha256": sha256_file(archive_path), "archive_bytes": archive_path.stat().st_size,
                    "expanded_bytes": sum(e["bytes"] for e in files)}
        validate_manifest(manifest)
        if len((json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")) > MAX_MANIFEST:
            raise ValueError("Bundle manifest exceeds transport limit")
        write(destination / "bundle.json", manifest)
    return manifest


def import_bundle(source, destination):
    try:
        return _import_bundle(source, destination)
    except (zipfile.BadZipFile, zipfile.LargeZipFile, zlib.error, EOFError, NotImplementedError) as error:
        raise ValueError("Invalid or unsupported deployment archive: " + str(error)) from error


def _import_bundle(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    manifest_path = source / "bundle.json" if source.is_dir() else source
    if manifest_path.is_symlink() or manifest_path.stat().st_size > MAX_MANIFEST:
        raise ValueError("Invalid bundle manifest file")
    manifest = validate_manifest(load(manifest_path))
    if destination.exists():
        raise FileExistsError("Import requires a new directory")
    with tempfile.TemporaryDirectory(prefix="cantos-deployment-import-") as scratch:
        archive_path = Path(scratch) / "evidence.zip"
        with archive_path.open("xb") as output:
            for entry in manifest["parts"]:
                path = manifest_path.parent / entry["path"]
                if path.is_symlink() or not path.is_file() or path.stat().st_size != entry["bytes"] or sha256_file(path) != entry["sha256"]:
                    raise ValueError("Missing or altered bundle part: " + entry["path"])
                with path.open("rb") as part:
                    shutil.copyfileobj(part, output, length=1024 * 1024)
        if sha256_file(archive_path) != manifest["archive_sha256"]:
            raise ValueError("Reassembled archive digest mismatch")
        expected = {e["path"]: e for e in manifest["files"]}
        with zipfile.ZipFile(archive_path) as archive:
            infos = archive.infolist()
            if len(infos) != len(expected):
                raise ValueError("Archive membership differs from manifest")
            seen = set()
            for info in infos:
                name = safe_name(info.filename)
                mode = info.external_attr >> 16
                if name in seen or name not in expected or info.is_dir() or info.flag_bits & 1 or stat.S_IFMT(mode) not in (0, stat.S_IFREG):
                    raise ValueError("Invalid archive member")
                seen.add(name)
                if info.file_size != expected[name]["bytes"]:
                    raise ValueError("Expanded member size mismatch")
                hasher = hashlib.sha256()
                count = 0
                with archive.open(info) as stream:
                    while data := stream.read(1024 * 1024):
                        count += len(data)
                        if count > expected[name]["bytes"]:
                            raise ValueError("Expanded member exceeds declared size")
                        hasher.update(data)
                if count != expected[name]["bytes"] or hasher.hexdigest() != expected[name]["sha256"]:
                    raise ValueError("Expanded member hash mismatch")
            # Every member is checked before any imported file becomes visible.
            destination.mkdir(parents=True, exist_ok=False)
            for info in infos:
                target = destination / info.filename
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as stream, target.open("xb") as output:
                    shutil.copyfileobj(stream, output, length=1024 * 1024)
    return {"root": str(destination), "record": str(destination / manifest["record"]), "manifest": manifest}
