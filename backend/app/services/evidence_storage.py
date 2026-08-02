from __future__ import annotations
import hashlib
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO
from uuid import uuid4

from fastapi import HTTPException, UploadFile
from app.core.config import get_settings

ALLOWED_CONTENT_TYPES = {
    "application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "image/jpeg", "image/png", "text/plain", "text/csv", "application/json",
}
EICAR_SIGNATURE = b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE"


@dataclass(frozen=True)
class StoredUpload:
    storage_uri: str
    sha256: str
    size_bytes: int
    scan_status: str
    scan_message: str | None


def safe_file_name(value: str) -> str:
    name = Path(value or "evidence.bin").name
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")
    return name[:180] or "evidence.bin"


def _validate_signature(content_type: str, head: bytes) -> None:
    signatures = {
        "application/pdf": b"%PDF-",
        "image/png": b"\x89PNG\r\n\x1a\n",
        "image/jpeg": b"\xff\xd8\xff",
    }
    expected = signatures.get(content_type)
    if expected and not head.startswith(expected):
        raise HTTPException(status_code=422, detail="File signature does not match content type")
    if content_type in {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    } and not head.startswith(b"PK"):
        raise HTTPException(status_code=422, detail="Office file is not a valid ZIP container")


def _basic_scan(path: Path) -> tuple[str, str | None]:
    settings = get_settings()
    if settings.antivirus_mode == "disabled":
        return "Clean", "Antivirus disabled by configuration"
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(1024 * 1024)
            if not chunk:
                break
            if EICAR_SIGNATURE in chunk:
                return "Rejected", "EICAR test signature detected"
    return "Clean", "Basic signature scan passed"


def store_upload(upload: UploadFile, key_prefix: str) -> StoredUpload:
    settings = get_settings()
    content_type = (upload.content_type or "application/octet-stream").lower()
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=415, detail=f"Unsupported content type: {content_type}")

    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    digest = hashlib.sha256()
    size = 0
    first = b""
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(prefix="pios-evidence-", delete=False) as tmp:
            temp_path = Path(tmp.name)
            while True:
                chunk = upload.file.read(1024 * 1024)
                if not chunk:
                    break
                if not first:
                    first = chunk[:32]
                size += len(chunk)
                if size > max_bytes:
                    raise HTTPException(status_code=413, detail=f"File exceeds {settings.max_upload_size_mb} MB")
                digest.update(chunk)
                tmp.write(chunk)
        if size == 0:
            raise HTTPException(status_code=422, detail="Empty files are not accepted")
        _validate_signature(content_type, first)
        scan_status, scan_message = _basic_scan(temp_path)
        if scan_status != "Clean":
            raise HTTPException(status_code=422, detail=scan_message or "File rejected by antivirus")

        filename = safe_file_name(upload.filename or "evidence.bin")
        object_key = f"{key_prefix.strip('/')}/{uuid4()}_{filename}"
        if settings.object_storage_backend == "s3":
            import boto3
            client = boto3.client(
                "s3", endpoint_url=settings.s3_endpoint_url,
                aws_access_key_id=settings.s3_access_key,
                aws_secret_access_key=settings.s3_secret_key,
                region_name=settings.s3_region,
            )
            client.upload_file(str(temp_path), settings.object_storage_bucket, object_key,
                               ExtraArgs={"ContentType": content_type})
            uri = f"s3://{settings.object_storage_bucket}/{object_key}"
        else:
            root = Path(settings.object_storage_root).resolve()
            destination = (root / object_key).resolve()
            if root not in destination.parents:
                raise HTTPException(status_code=422, detail="Invalid storage key")
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.replace(temp_path, destination)
            temp_path = None
            uri = destination.as_uri()
        return StoredUpload(
            storage_uri=uri, sha256=digest.hexdigest(), size_bytes=size,
            scan_status=scan_status, scan_message=scan_message,
        )
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink(missing_ok=True)


def local_path_from_uri(storage_uri: str) -> Path | None:
    if not storage_uri.startswith("file://"):
        return None
    return Path(storage_uri.removeprefix("file://"))
