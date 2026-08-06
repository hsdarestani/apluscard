from __future__ import annotations

import base64
import io
import shutil
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHUNKS = ROOT / "ops" / "patch_chunks"


def _safe_extract(archive: tarfile.TarFile, destination: Path) -> None:
    destination = destination.resolve()
    for member in archive.getmembers():
        target = (destination / member.name).resolve()
        if destination not in target.parents and target != destination:
            raise RuntimeError(f"Unsafe archive path: {member.name}")
    archive.extractall(destination)


def main() -> None:
    parts = sorted(CHUNKS.glob("part*"))
    if not parts:
        raise RuntimeError("Patch payload chunks are missing")
    encoded = "".join(part.read_text(encoding="ascii").strip() for part in parts)
    payload = base64.b64decode(encoded, validate=True)
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
        _safe_extract(archive, ROOT)

    shutil.rmtree(CHUNKS, ignore_errors=True)
    Path(__file__).unlink(missing_ok=True)


if __name__ == "__main__":
    main()
