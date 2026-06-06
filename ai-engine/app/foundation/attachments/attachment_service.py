"""Local text extraction for PDF and Word document attachments.

Strategy (Path B): text is extracted in-process, then concatenated to the
transcript with a clear separator before being passed to the LLM prompt.
This keeps the solution provider-agnostic and lays the groundwork for
RAG chunking in a later module.

Supported MIME types / extensions:
  - application/pdf  (.pdf)  → pypdf
  - application/vnd.openxmlformats-officedocument.wordprocessingml.document
    (.docx)  → python-docx
  - text/plain  (.txt)  → decoded as UTF-8

All other types raise :class:`UnsupportedAttachmentType`.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

import structlog

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Sentinel separator injected between the transcript and each attachment
# ---------------------------------------------------------------------------

ATTACHMENT_SEPARATOR = "--- attachment: {filename} ---"


# ---------------------------------------------------------------------------
# Domain exceptions
# ---------------------------------------------------------------------------


class UnsupportedAttachmentType(ValueError):
    """Raised when an uploaded file's content type is not supported."""

    def __init__(self, filename: str, content_type: str) -> None:
        super().__init__(
            f"Unsupported attachment type '{content_type}' for file '{filename}'. "
            "Allowed: PDF, DOCX, plain text."
        )
        self.filename = filename
        self.content_type = content_type


class AttachmentExtractionError(RuntimeError):
    """Raised when text extraction fails for an otherwise supported file."""

    def __init__(self, filename: str, cause: Exception) -> None:
        super().__init__(f"Failed to extract text from '{filename}': {cause}")
        self.filename = filename
        self.cause = cause


# ---------------------------------------------------------------------------
# Internal data container
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExtractedAttachment:
    filename: str
    text: str


# ---------------------------------------------------------------------------
# Low-level extractors (synchronous – run in a thread pool for async callers)
# ---------------------------------------------------------------------------


def _extract_pdf(data: bytes, filename: str) -> str:
    try:
        import pypdf  # noqa: PLC0415  (deferred import keeps startup fast)
    except ImportError as exc:
        raise RuntimeError(
            "pypdf is required for PDF extraction. "
            "Install it with: uv add pypdf"
        ) from exc

    try:
        reader = pypdf.PdfReader(io.BytesIO(data))
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n".join(pages).strip()
    except Exception as exc:
        raise AttachmentExtractionError(filename, exc) from exc


def _extract_docx(data: bytes, filename: str) -> str:
    try:
        import docx  # noqa: PLC0415
    except ImportError as exc:
        raise RuntimeError(
            "python-docx is required for DOCX extraction. "
            "Install it with: uv add python-docx"
        ) from exc

    try:
        doc = docx.Document(io.BytesIO(data))
        paragraphs = [para.text for para in doc.paragraphs if para.text.strip()]
        return "\n".join(paragraphs).strip()
    except Exception as exc:
        raise AttachmentExtractionError(filename, exc) from exc


def _extract_plain_text(data: bytes, filename: str) -> str:
    try:
        return data.decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise AttachmentExtractionError(filename, exc) from exc


# ---------------------------------------------------------------------------
# Public service
# ---------------------------------------------------------------------------


class AttachmentService:
    """Extracts text from uploaded files and builds a combined transcript."""

    # Map of content-type prefix → extractor function
    _EXTRACTORS = {
        "application/pdf": _extract_pdf,
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": _extract_docx,
        "text/plain": _extract_plain_text,
    }

    def extract(self, filename: str, content_type: str, data: bytes) -> ExtractedAttachment:
        """Extract text from *data* according to *content_type*.

        Args:
            filename: Original filename, used in log messages and separators.
            content_type: MIME type reported by the HTTP client.
            data: Raw file bytes.

        Returns:
            :class:`ExtractedAttachment` with the extracted text.

        Raises:
            UnsupportedAttachmentType: When the content type is not in the allow-list.
            AttachmentExtractionError: When extraction fails for a supported type.
        """
        # Normalise: strip params like charset=utf-8
        base_type = content_type.split(";")[0].strip().lower()

        # Fall back to extension-based detection when content_type is generic
        if base_type in ("application/octet-stream", ""):
            base_type = self._sniff_by_extension(filename)

        extractor = self._EXTRACTORS.get(base_type)
        if extractor is None:
            raise UnsupportedAttachmentType(filename, content_type)

        log.info("attachment_extraction_started", filename=filename, content_type=base_type)
        text = extractor(data, filename)
        log.info(
            "attachment_extraction_completed",
            filename=filename,
            extracted_chars=len(text),
        )
        return ExtractedAttachment(filename=filename, text=text)

    @staticmethod
    def _sniff_by_extension(filename: str) -> str:
        lower = filename.lower()
        if lower.endswith(".pdf"):
            return "application/pdf"
        if lower.endswith(".docx"):
            return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        if lower.endswith(".txt"):
            return "text/plain"
        return ""

    def build_combined_transcript(
        self,
        transcript: str,
        attachments: list[ExtractedAttachment],
    ) -> str:
        """Concatenate *transcript* with each attachment using a clear separator.

        Example output::

            <original transcript text>

            --- attachment: spec.pdf ---
            <extracted PDF text>

            --- attachment: notes.docx ---
            <extracted DOCX text>
        """
        if not attachments:
            return transcript

        parts: list[str] = [transcript.strip()]
        for att in attachments:
            separator = ATTACHMENT_SEPARATOR.format(filename=att.filename)
            parts.append(f"\n{separator}\n{att.text}")

        return "\n".join(parts)
