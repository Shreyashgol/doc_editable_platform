"""Synchronous upload validation (no heavy deps).

Order is fail-closed: size → magic bytes → MIME → filename sanitization. Deep structural
safety (page/pixel PDF-bomb caps) needs PyMuPDF and runs in the worker's VALIDATE stage, so the
API process stays light. See docs/03 security pipeline.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from ...core.config import Settings
from ...core.errors import FileValidationError

_PDF_MAGIC = b"%PDF-"
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass(frozen=True, slots=True)
class ValidatedUpload:
    filename: str
    content_hash: str
    size_bytes: int
    mime_type: str


def sanitize_filename(name: str) -> str:
    base = name.rsplit("/", 1)[-1].rsplit("\\", 1)[-1].strip()
    base = _SAFE_NAME.sub("_", base) or "upload.pdf"
    if not base.lower().endswith(".pdf"):
        base += ".pdf"
    return base[:255]


class FileValidator:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def validate(self, *, filename: str, content: bytes, declared_mime: str) -> ValidatedUpload:
        size = len(content)
        if size == 0:
            raise FileValidationError("uploaded file is empty")
        if size > self._settings.max_upload_bytes:
            raise FileValidationError(
                f"file exceeds maximum size of {self._settings.max_upload_bytes} bytes"
            )
        if not content.startswith(_PDF_MAGIC):
            raise FileValidationError("file is not a valid PDF (magic bytes mismatch)")
        if declared_mime not in self._settings.allowed_mime_types:
            raise FileValidationError(f"unsupported content type: {declared_mime}")

        return ValidatedUpload(
            filename=sanitize_filename(filename),
            content_hash=hashlib.sha256(content).hexdigest(),
            size_bytes=size,
            mime_type="application/pdf",
        )
