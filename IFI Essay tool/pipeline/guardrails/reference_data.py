from __future__ import annotations

import csv
import os
import re
from difflib import SequenceMatcher
from pathlib import Path


def _normalize_school_text(value: str) -> str:
    text = (value or "").casefold()
    text = re.sub(r"[^a-z0-9\s]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


class SchoolReferenceValidator:
    def __init__(self, csv_path: str | None = None):
        env_path = os.environ.get("SCHOOL_REFERENCE_CSV_PATH")
        default_path = (
            Path(__file__).resolve().parents[2] / "reference_data" / "schools.csv"
        )
        self.csv_path = Path(csv_path or env_path or default_path)
        self._rows = self._load_rows()
        self.reference_version = f"{self.csv_path.name}:{len(self._rows)}"
        self._normalized_rows = [_normalize_school_text(row) for row in self._rows]

    def _load_rows(self) -> list[str]:
        if not self.csv_path.exists():
            return []
        rows: list[str] = []
        with open(self.csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for item in reader:
                school = (item.get("school_name") or "").strip()
                if school:
                    rows.append(school)
        return rows

    def validate(self, school_name: str | None) -> dict:
        if not school_name or not str(school_name).strip():
            return {
                "matched": False,
                "method": "missing",
                "confidence": 0.0,
                "reference_version": self.reference_version,
            }
        normalized = _normalize_school_text(str(school_name))
        if normalized in self._normalized_rows:
            return {
                "matched": True,
                "method": "exact",
                "confidence": 1.0,
                "reference_version": self.reference_version,
            }

        best_ratio = 0.0
        for ref in self._normalized_rows:
            ratio = SequenceMatcher(None, normalized, ref).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
        if best_ratio >= 0.9:
            return {
                "matched": True,
                "method": "fuzzy",
                "confidence": round(float(best_ratio), 6),
                "reference_version": self.reference_version,
            }

        return {
            "matched": False,
            "method": "none",
            "confidence": round(float(best_ratio), 6),
            "reference_version": self.reference_version,
        }

