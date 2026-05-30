"""Generate synthetic PDF files of calibrated sizes for attachment stress testing.

Uses a repeated Lorem Ipsum text to create PDFs of specific byte sizes:
- 0 KB (no attachment, baseline)
- 5 KB (≈ 2 pages of plain text)
- 20 KB (≈ 8 pages)
- 50 KB (≈ 20 pages)
- 100 KB (near the MAX_ATTACHMENT_CHARS=60,000 limit; tests truncation)

Each PDF is generated with extractable text content for recall measurement.
"""

from __future__ import annotations

import io
import textwrap
from pathlib import Path

# Try to import reportlab; if not available, fall back to text-only PDFs
try:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas as reportlab_canvas
    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False


# Lorem Ipsum base text for padding
_LOREM_IPSUM = """\
Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor \
incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis \
nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat. \
Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore \
eu fugiat nulla pariatur. Excepteur sint occaecat cupidatat non proident, sunt \
in culpa qui officia deserunt mollit anim id est laborum.
"""

_LOREM_SENTENCE = "Lorem ipsum dolor sit amet, consectetur adipiscing elit."
_LOREM_PARAGRAPH = _LOREM_IPSUM.strip()


def _create_pdf_reportlab(target_size_kb: int, title: str) -> bytes:
    """Create a PDF using reportlab with text sized to approximately target_size_kb.
    
    Args:
        target_size_kb: Target approximate size in KB.
        title: Title for the PDF.
    
    Returns:
        PDF as bytes.
    """
    if not HAS_REPORTLAB:
        return _create_pdf_text(target_size_kb, title)
    
    buffer = io.BytesIO()
    c = reportlab_canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    
    # Title
    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, height - 50, title)
    
    # Calculate how much text we need
    # Empirically, about 3000-4000 bytes per page at 11pt Helvetica
    bytes_per_page = 3500
    target_bytes = target_size_kb * 1024
    num_pages = max(1, target_bytes // bytes_per_page)
    
    # Font and layout
    c.setFont("Helvetica", 11)
    y = height - 100
    left_margin = 50
    right_margin = width - 50
    line_height = 14
    
    text_lines = _LOREM_PARAGRAPH.split()
    line_idx = 0
    page_count = 0
    
    # Fill pages with Lorem Ipsum
    while page_count < num_pages:
        x = left_margin
        while y > 50 and page_count < num_pages:
            # Build a line of text
            line = ""
            while line_idx < len(text_lines):
                word = text_lines[line_idx]
                test_line = f"{line} {word}".strip()
                if c.stringWidth(test_line, "Helvetica", 11) > (right_margin - left_margin):
                    break
                line = test_line
                line_idx += 1
            
            if not line:
                # Move to next word if current word is too long
                if line_idx < len(text_lines):
                    line = text_lines[line_idx]
                    line_idx += 1
            
            if line:
                c.drawString(left_margin, y, line)
                y -= line_height
            else:
                break
        
        if page_count < num_pages - 1:
            c.showPage()
            page_count += 1
            y = height - 50
    
    c.save()
    pdf_bytes = buffer.getvalue()
    return pdf_bytes


def _create_pdf_text(target_size_kb: int, title: str) -> bytes:
    """Fallback: create a simple text file (with PDF-like structure) if reportlab unavailable.
    
    Since we mostly care about text extraction and file size, a text file works for testing.
    """
    target_bytes = target_size_kb * 1024
    
    # Build text by repeating Lorem Ipsum
    text_parts = [f"Title: {title}\n\n"]
    current_size = len(text_parts[0])
    
    while current_size < target_bytes:
        text_parts.append(_LOREM_PARAGRAPH)
        text_parts.append("\n\n")
        current_size = sum(len(p) for p in text_parts)
    
    full_text = "".join(text_parts)
    # Trim to exact target size
    full_text = full_text[:target_bytes]
    
    return full_text.encode("utf-8")


def generate_pdf(size_kb: int, filename: str | Path | None = None) -> bytes:
    """Generate a synthetic PDF of approximately the given size in KB.
    
    Args:
        size_kb: Target size in KB (0, 5, 20, 50, 100).
        filename: Optional filepath to write the PDF to. If None, returns bytes only.
    
    Returns:
        PDF content as bytes.
    """
    if size_kb == 0:
        # Special case: no attachment
        pdf_bytes = b""
    else:
        title = f"Synthetic Attachment - Approximately {size_kb} KB"
        try:
            pdf_bytes = _create_pdf_reportlab(size_kb, title)
        except Exception:
            # Fallback to text-only
            pdf_bytes = _create_pdf_text(size_kb, title)
    
    if filename:
        Path(filename).write_bytes(pdf_bytes)
    
    return pdf_bytes


def get_standard_sizes() -> dict[int, str]:
    """Return standard attachment sizes for testing.
    
    Returns:
        Mapping of size_kb -> description.
    """
    return {
        0: "No attachment (baseline)",
        5: "~2 pages of text (5 KB)",
        20: "~8 pages (20 KB)",
        50: "~20 pages (50 KB)",
        100: "~40 pages, near MAX_ATTACHMENT_CHARS limit (100 KB)",
    }
