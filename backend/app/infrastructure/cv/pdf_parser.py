"""PyMuPDF PDF parser adapter.

``fitz`` is imported lazily inside methods so importing this module (and therefore the worker
package) does not require PyMuPDF to be installed in environments that only need the ports.
"""

from __future__ import annotations

from ...core.errors import PdfBombError, ProcessingError
from ...domain.ports import PdfParser


class PyMuPdfParser(PdfParser):
    def page_count(self, pdf_bytes: bytes) -> int:
        import fitz

        try:
            with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
                return doc.page_count
        except Exception as exc:
            raise ProcessingError(f"failed to open PDF: {exc}") from exc

    def validate_safety(
        self, pdf_bytes: bytes, *, max_pages: int, max_page_pixels: int
    ) -> None:
        import fitz

        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        except Exception as exc:
            raise ProcessingError(f"failed to open PDF: {exc}") from exc
        with doc:
            if doc.page_count == 0:
                raise ProcessingError("PDF has no pages")
            if doc.page_count > max_pages:
                raise PdfBombError(
                    f"PDF has {doc.page_count} pages (limit {max_pages})"
                )
            for page in doc:
                rect = page.rect
                # Pixel budget at 1x; rendering DPI multiplies this, so cap conservatively.
                pixels = int(rect.width * rect.height)
                if pixels > max_page_pixels:
                    raise PdfBombError(
                        f"page {page.number} is {pixels}px (limit {max_page_pixels})"
                    )

    def render_pages(
        self, pdf_bytes: bytes, dpi: int
    ) -> list[tuple[int, bytes, int, int]]:
        import fitz

        out: list[tuple[int, bytes, int, int]] = []
        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            zoom = dpi / 72.0
            matrix = fitz.Matrix(zoom, zoom)
            for page in doc:
                pix = page.get_pixmap(matrix=matrix, alpha=False)
                out.append((page.number + 1, pix.tobytes("png"), pix.width, pix.height))
        return out
