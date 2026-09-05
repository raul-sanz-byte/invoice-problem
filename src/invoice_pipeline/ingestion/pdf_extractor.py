from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from invoice_pipeline.llm_client import LLMClient


def extract_spatial_pdf_text(file_path: str | Path) -> str:
    """Extract text from a PDF with spatial row & column alignment preservation.

    Groups text lines by Y-coordinate so side-by-side elements (e.g. 'Vendor:' and
    'Summit Manufacturing Co.', or table rows) appear on the same line in natural reading order.
    """
    try:
        from pdfminer.high_level import extract_pages
        from pdfminer.layout import LTTextContainer, LTTextLine

        pages_text: list[str] = []
        for page_layout in extract_pages(str(file_path)):
            lines_with_pos: list[tuple[float, float, str]] = []
            for element in page_layout:
                if isinstance(element, LTTextContainer):
                    for text_line in element:
                        if isinstance(text_line, LTTextLine):
                            t = text_line.get_text().strip()
                            if t:
                                lines_with_pos.append((text_line.bbox[1], text_line.bbox[0], t))
            if not lines_with_pos:
                continue

            # Sort top to bottom by y coordinate
            lines_with_pos.sort(key=lambda item: -item[0])
            grouped_rows: list[dict] = []
            for y, x, text in lines_with_pos:
                matched = False
                for row in grouped_rows:
                    if abs(row["y"] - y) <= 4.0:
                        row["items"].append((x, text))
                        matched = True
                        break
                if not matched:
                    grouped_rows.append({"y": y, "items": [(x, text)]})

            page_lines: list[str] = []
            for row in grouped_rows:
                row["items"].sort(key=lambda it: it[0])
                page_lines.append("    ".join(it[1] for it in row["items"]))
            pages_text.append("\n".join(page_lines))

        result = "\n\n".join(pages_text).strip()
        if result:
            return result
    except Exception:
        pass

    # Fallback to standard pdfminer extract_text if spatial extraction fails
    try:
        from pdfminer.high_level import extract_text
        return extract_text(str(file_path)).strip()
    except Exception:
        return ""


def extract_from_pdf(file_path: str | Path, llm_client: "LLMClient | None" = None) -> str:
    """PDF text extraction using spatial layout reconstruction with multimodal LLM fallback."""
    # 1. Primary: Fast, deterministic spatial text extraction preserving table/row layout
    text = extract_spatial_pdf_text(file_path)
    if text:
        return text

    # 2. Fallback: Multimodal LLM (for scanned / raster image PDFs)
    if llm_client is not None:
        try:
            return llm_client.extract_text_from_pdf(file_path)
        except Exception:
            pass

    return ""
