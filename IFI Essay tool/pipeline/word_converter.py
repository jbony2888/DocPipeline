"""
Convert Word documents (.doc, .docx) to PDF for pipeline processing.
"""

import logging
import os
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


def convert_word_to_pdf(word_path: str) -> str | None:
    """
    Convert a Word document to PDF. Returns path to the generated PDF, or None on failure.

    Tries in order:
    1. LibreOffice (headless) - best formatting preservation, works for .doc and .docx
    2. python-docx + reportlab - .docx only, text extraction

    Args:
        word_path: Path to .doc or .docx file

    Returns:
        Path to temporary PDF file (caller must delete), or None if conversion failed
    """
    path = Path(word_path)
    ext = path.suffix.lower()
    if ext not in (".doc", ".docx"):
        logger.warning(f"word_converter: unsupported extension {ext}")
        return None

    # Try LibreOffice first (common on Linux servers, Render, etc.)
    pdf_path = _convert_via_libreoffice(word_path)
    if pdf_path:
        return pdf_path

    # Fallback: python-docx + reportlab (.docx only)
    if ext == ".docx":
        pdf_path = _convert_docx_via_python(word_path)
        if pdf_path:
            return pdf_path

    if ext == ".doc":
        logger.warning(
            "Word .doc conversion failed. LibreOffice is not installed. "
            "Please convert the file to .docx or PDF before uploading."
        )
    return None


def _convert_via_libreoffice(word_path: str) -> str | None:
    """Use LibreOffice headless to convert. Returns PDF path or None."""
    for cmd in (["libreoffice", "--headless"], ["soffice", "--headless"]):
        try:
            out_dir = tempfile.mkdtemp(prefix="word_conv_")
            result = subprocess.run(
                cmd + ["--convert-to", "pdf", "--outdir", out_dir, word_path],
                capture_output=True,
                timeout=60,
            )
            if result.returncode != 0:
                continue
            base = Path(word_path).stem
            pdf_path = Path(out_dir) / f"{base}.pdf"
            if pdf_path.exists():
                # Move to a temp file we can pass to the pipeline (caller will delete)
                fd, tmp_pdf = tempfile.mkstemp(suffix=".pdf", prefix="word_converted_")
                os.close(fd)
                with open(pdf_path, "rb") as f:
                    with open(tmp_pdf, "wb") as out:
                        out.write(f.read())
                try:
                    import shutil
                    shutil.rmtree(out_dir)
                except Exception:
                    pass
                logger.info(f"Converted Word to PDF via LibreOffice: {Path(word_path).name}")
                return tmp_pdf
        except (FileNotFoundError, subprocess.TimeoutExpired, Exception) as e:
            logger.debug(f"LibreOffice conversion failed: {e}")
            continue
    return None


def _convert_docx_via_python(word_path: str) -> str | None:
    """Extract text from .docx and create a simple PDF using python-docx + reportlab."""
    try:
        from docx import Document
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import inch
        from reportlab.platypus import SimpleDocTemplate, Paragraph
    except ImportError as e:
        logger.warning(f"python-docx or reportlab not installed: {e}")
        return None

    try:
        doc = Document(word_path)
        paragraphs = []
        for p in doc.paragraphs:
            text = (p.text or "").strip()
            if text:
                paragraphs.append(text)

        if not paragraphs:
            logger.warning("docx has no extractable text")
            return None

        fd, tmp_pdf = tempfile.mkstemp(suffix=".pdf", prefix="word_converted_")
        os.close(fd)

        story = []
        styles = getSampleStyleSheet()
        for text in paragraphs:
            # Escape XML special chars for Paragraph
            safe = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            story.append(Paragraph(safe, styles["Normal"]))

        doc_template = SimpleDocTemplate(tmp_pdf, pagesize=letter, leftMargin=inch, rightMargin=inch)
        doc_template.build(story)

        logger.info(f"Converted docx to PDF via python-docx+reportlab: {Path(word_path).name}")
        return tmp_pdf
    except Exception as e:
        logger.warning(f"docx conversion failed: {e}")
        return None
