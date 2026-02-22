from __future__ import annotations

from idp_guardrails_core.core import DocRole, classify_doc_role as _classify_doc_role


def classify_doc_role(
    record: dict | None,
    report: dict | None,
    chunk_metadata: dict | None = None,
) -> DocRole:
    rec = dict(record or {})
    rep = dict(report or {})
    if "doc_class" in rec and hasattr(rec.get("doc_class"), "value"):
        rec["doc_class"] = rec["doc_class"].value
    ex_debug = dict((rep.get("extraction_debug") or {}))
    if "doc_class" in ex_debug and hasattr(ex_debug.get("doc_class"), "value"):
        ex_debug["doc_class"] = ex_debug["doc_class"].value
        rep["extraction_debug"] = ex_debug
    return _classify_doc_role(rec, rep, chunk_metadata=chunk_metadata)

