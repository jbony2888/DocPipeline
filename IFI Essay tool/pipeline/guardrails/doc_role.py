from __future__ import annotations

from enum import Enum
from typing import Any

from pipeline.schema import DocClass


class DocRole(str, Enum):
    CONTAINER = "container"
    DOCUMENT = "document"


def _coerce_doc_class(value: Any) -> DocClass | None:
    if isinstance(value, DocClass):
        return value
    if isinstance(value, str):
        try:
            return DocClass(value)
        except ValueError:
            return None
    return None


def _has_chunk_index(chunk_metadata: dict | None, record: dict | None) -> bool:
    if isinstance(chunk_metadata, dict) and chunk_metadata.get("chunk_index") is not None:
        return True
    if isinstance(record, dict) and record.get("chunk_index") is not None:
        return True
    return False


def classify_doc_role(
    record: dict | None,
    report: dict | None,
    chunk_metadata: dict | None = None,
) -> DocRole:
    """
    Canonical classifier for container vs document roles.

    Rules:
    - chunk_index present -> DOCUMENT
    - multi-structure or BULK_SCANNED_BATCH without chunk_index -> CONTAINER
    - default -> DOCUMENT
    """
    if _has_chunk_index(chunk_metadata, record):
        return DocRole.DOCUMENT

    rec = record or {}
    rep = report or {}

    structure = (
        rec.get("analysis_structure")
        or rec.get("structure")
        or (rep.get("analysis") or {}).get("structure")
        or (rep.get("extraction_debug") or {}).get("analysis_structure")
    )
    doc_class = _coerce_doc_class(rec.get("doc_class"))
    if doc_class is None:
        doc_class = _coerce_doc_class((rep.get("extraction_debug") or {}).get("doc_class"))

    if bool(rec.get("is_container_parent")):
        return DocRole.CONTAINER
    if structure == "multi" or doc_class == DocClass.BULK_SCANNED_BATCH:
        return DocRole.CONTAINER
    return DocRole.DOCUMENT

