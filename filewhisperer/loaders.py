"""Turn files into a list of (page_label, text) pairs.

Every format is read into memory as raw bytes up front, and every loader
works from those bytes rather than a file path — see the note in
load_pages() for why. Documents that have a real notion of pages (PDFs,
spreadsheet sheets) preserve it, so a chunk built from this text can later
be cited back to "Report.pdf, page 3" instead of just "Report.pdf".

Add a new format by writing a `_load_xxx(data: bytes) -> list[Page]`
function and registering its extension in load_pages().
"""

from __future__ import annotations

import concurrent.futures
import io
import os
from dataclasses import dataclass
from pathlib import Path

PLAIN_TEXT_EXTENSIONS = {".txt", ".md", ".csv", ".json", ".log"}


@dataclass
class Page:
    label: str | None  # e.g. "page 3", "Sheet1 (rows 1-100)", or None if the format has no pages
    text: str


def _int_env(name: str, default: int, legacy_name: str | None = None) -> int:
    try:
        value = os.environ.get(name)
        if value is None and legacy_name:
            value = os.environ.get(legacy_name)
        return int(value if value is not None else default)
    except (TypeError, ValueError):
        return default


def _float_env(name: str, default: float, legacy_name: str | None = None) -> float:
    try:
        value = os.environ.get(name)
        if value is None and legacy_name:
            value = os.environ.get(legacy_name)
        return float(value if value is not None else default)
    except (TypeError, ValueError):
        return default


# --- OCR tuning knobs -------------------------------------------------------
OCR_MAX_PAGES = _int_env("FILEWHISPERER_OCR_MAX_PAGES", 20, "DOCUMIND_OCR_MAX_PAGES")
OCR_MAX_WORKERS = _int_env("FILEWHISPERER_OCR_MAX_WORKERS", min(4, os.cpu_count() or 1), "DOCUMIND_OCR_MAX_WORKERS")
OCR_RENDER_SCALE = _float_env("FILEWHISPERER_OCR_RENDER_SCALE", 2.0, "DOCUMIND_OCR_RENDER_SCALE")
OCR_CONFIDENCE_OK = _float_env("FILEWHISPERER_OCR_CONFIDENCE_OK", 40.0, "DOCUMIND_OCR_CONFIDENCE_OK")

# A PDF page is treated as "multi-column" (and read column-by-column,
# top-to-bottom in each, instead of straight top-to-bottom across the whole
# width) when the single biggest horizontal gap between word start-x's is
# at least this fraction of the page width. Plain sentence/word spacing
# never gets close to this, so normal single-column pages aren't affected.
COLUMN_GAP_RATIO = _float_env("FILEWHISPERER_COLUMN_GAP_RATIO", 0.08, "DOCUMIND_COLUMN_GAP_RATIO")

# Spreadsheet sheets longer than this are split into multiple "pages" of
# this many rows each, so one huge sheet doesn't become one enormous chunk.
XLSX_ROWS_PER_PAGE = _int_env("FILEWHISPERER_XLSX_ROWS_PER_PAGE", 150, "DOCUMIND_XLSX_ROWS_PER_PAGE")


class UnsupportedFileType(Exception):
    """Raised when a file extension has no registered loader."""


class EmptyDocument(Exception):
    """Raised when a file was read but no usable text came out of it."""


class OcrUnavailable(Exception):
    """Raised when OCR was needed but a required piece isn't installed or working."""


def _load_plain_text(data: bytes) -> list[Page]:
    return [Page(label=None, text=data.decode("utf-8", errors="replace"))]


# --- PDF: digital text, with column-aware extraction and per-page OCR ------

def _extract_page_text(page) -> str:
    """Extract one pdfplumber page's text, reading column-by-column (each
    column top-to-bottom) if the page looks like it has multiple columns,
    instead of pdfplumber's default which can interleave column lines."""
    words = page.extract_words()
    if not words:
        return page.extract_text() or ""

    xs = sorted(w["x0"] for w in words)
    gaps = [(xs[i + 1] - xs[i], xs[i], xs[i + 1]) for i in range(len(xs) - 1)]
    if not gaps:
        return page.extract_text() or ""
    biggest_gap, left_x, right_x = max(gaps)

    if biggest_gap < page.width * COLUMN_GAP_RATIO:
        return page.extract_text() or ""  # normal single-column page

    split_x = (left_x + right_x) / 2
    left_text = page.within_bbox((0, 0, split_x, page.height)).extract_text() or ""
    right_text = page.within_bbox((split_x, 0, page.width, page.height)).extract_text() or ""
    return (left_text + "\n\n" + right_text).strip()


def _digital_pdf_pages(data: bytes) -> list[str]:
    """Try pdfplumber (column-aware) first; fall back to plain pypdf if
    pdfplumber can't open the file for some reason. Returns one string per
    page, in order (empty string for a page with no extractable text)."""
    try:
        import pdfplumber

        with pdfplumber.open(io.BytesIO(data)) as pdf:
            return [_extract_page_text(p) for p in pdf.pages]
    except Exception:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        return [page.extract_text() or "" for page in reader.pages]


def _ocr_one_page(pdf_bytes: bytes, page_index: int, scale: float) -> str:
    """Render and OCR a single page. Runs in a worker thread, so it opens
    its own PdfDocument from the shared (immutable) bytes rather than
    sharing one document object across threads."""
    import pypdfium2 as pdfium
    import pytesseract
    from pytesseract import Output
    from PIL import ImageOps

    pdf = pdfium.PdfDocument(pdf_bytes)
    try:
        page = pdf[page_index]
        bitmap = page.render(scale=scale)
        base_image = bitmap.to_pil().convert("L")
    finally:
        pdf.close()

    config = "--oem 1"

    def confidence(image) -> float:
        try:
            data = pytesseract.image_to_data(image, config=config, output_type=Output.DICT)
        except Exception:
            return -1.0
        scores = [float(c) for c in data.get("conf", []) if str(c) != "-1"]
        return sum(scores) / len(scores) if scores else -1.0

    best_angle, best_conf = 0, confidence(base_image)
    if best_conf < OCR_CONFIDENCE_OK:
        for angle in (90, 180, 270):
            conf = confidence(base_image.rotate(angle, expand=True))
            if conf > best_conf:
                best_angle, best_conf = angle, conf

    oriented = base_image if best_angle == 0 else base_image.rotate(best_angle, expand=True)

    for variant in (
        oriented,
        ImageOps.autocontrast(oriented),
        oriented.point(lambda p: 0 if p < 140 else 255),
    ):
        text = pytesseract.image_to_string(variant, config=config)
        if text.strip():
            return text

    return ""


def _ocr_pages(data: bytes, page_indices: list[int]) -> dict[int, str]:
    """OCR just the given (0-based) page indices, in parallel. Returns a
    dict mapping page index -> extracted text (possibly empty on failure)."""
    try:
        import pypdfium2  # noqa: F401
        import pytesseract
    except ImportError as e:
        raise OcrUnavailable(
            "OCR packages aren't installed. Run: pip install pypdfium2 pytesseract Pillow"
        ) from e

    results: dict[int, str] = {}
    tesseract_missing: Exception | None = None

    with concurrent.futures.ThreadPoolExecutor(max_workers=OCR_MAX_WORKERS) as executor:
        future_to_index = {
            executor.submit(_ocr_one_page, data, i, OCR_RENDER_SCALE): i for i in page_indices
        }
        for future in concurrent.futures.as_completed(future_to_index):
            i = future_to_index[future]
            try:
                results[i] = future.result()
            except pytesseract.pytesseract.TesseractNotFoundError as e:
                tesseract_missing = e
                for f in future_to_index:
                    f.cancel()
                break
            except Exception:
                results[i] = ""

    if tesseract_missing is not None:
        raise OcrUnavailable(
            "the Tesseract OCR engine isn't installed or isn't on your PATH "
            "(see the README's OCR setup section for install steps)"
        ) from tesseract_missing

    return results


def _load_pdf(data: bytes, display_name: str) -> list[Page]:
    digital_texts = _digital_pdf_pages(data)
    page_count = len(digital_texts)

    # Per-page fallback: OCR only the pages that actually lack text, not
    # the whole document just because one page is a scanned insert. Capped
    # at OCR_MAX_PAGES so a document that's scanned throughout doesn't
    # hang forever.
    empty_indices = [i for i, t in enumerate(digital_texts) if not t.strip()]
    ocr_indices = empty_indices[:OCR_MAX_PAGES]

    ocr_results: dict[int, str] = {}
    ocr_error: OcrUnavailable | None = None
    if ocr_indices:
        try:
            ocr_results = _ocr_pages(data, ocr_indices)
        except OcrUnavailable as e:
            ocr_error = e  # only fatal if EVERY page ends up empty; see below

    pages: list[Page] = []
    for i, digital_text in enumerate(digital_texts):
        text = digital_text if digital_text.strip() else ocr_results.get(i, "")
        pages.append(Page(label=f"page {i + 1}", text=text))

    if not any(p.text.strip() for p in pages):
        if ocr_error is not None:
            raise EmptyDocument(
                f"'{display_name}' has no selectable text on any page, and OCR "
                f"couldn't read it either: {ocr_error}."
            )
        raise EmptyDocument(
            f"'{display_name}' has no selectable text — it's a scanned PDF, and OCR "
            "tried each page normally, then with extra contrast, then rotated in case "
            "it was sideways, and still found nothing readable."
        )

    return pages


def _load_docx(data: bytes) -> list[Page]:
    import docx

    document = docx.Document(io.BytesIO(data))
    parts = [p.text for p in document.paragraphs if p.text.strip()]
    for table in document.tables:
        for row in table.rows:
            parts.append(" | ".join(cell.text.strip() for cell in row.cells))
    return [Page(label=None, text="\n\n".join(parts))]


def _load_xlsx(data: bytes) -> list[Page]:
    """Each sheet becomes one or more 'pages' (split into row-batches if
    the sheet is long), rendered as a markdown table so both the model and
    a human reading the citation can make sense of it."""
    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True, read_only=True)
    pages: list[Page] = []

    for sheet in wb.worksheets:
        rows = list(sheet.iter_rows(values_only=True))
        rows = [r for r in rows if any(c is not None and str(c).strip() for c in r)]
        if not rows:
            continue

        header, body = rows[0], rows[1:]

        for start in range(0, max(len(body), 1), XLSX_ROWS_PER_PAGE):
            batch = body[start : start + XLSX_ROWS_PER_PAGE]
            lines = [
                "| " + " | ".join("" if c is None else str(c) for c in header) + " |",
                "| " + " | ".join("---" for _ in header) + " |",
            ]
            for row in batch:
                lines.append("| " + " | ".join("" if c is None else str(c) for c in row) + " |")

            if len(body) > XLSX_ROWS_PER_PAGE:
                label = f"{sheet.title} (rows {start + 1}-{start + len(batch)})"
            else:
                label = sheet.title
            pages.append(Page(label=label, text="\n".join(lines)))

    wb.close()
    return pages


def load_pages(path: str | Path, display_name: str | None = None) -> list[Page]:
    """Extract text from a supported file as a list of pages. `display_name`
    is used only in error messages — pass it when `path` is a temp file so
    errors refer to the real filename instead.

    The file is read into memory once, up front, and every loader below
    works from those bytes rather than the path itself. This is
    deliberate: letting pypdf/pypdfium2 hold a path open can leave a file
    handle alive until Python's garbage collector gets to it, and on
    Windows that can make a caller's immediate `os.unlink()` of the same
    path fail with "the process cannot access the file." Working from
    bytes avoids that entirely.

    Raises UnsupportedFileType, EmptyDocument, or FileNotFoundError if the
    file can't be turned into usable text.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"No such file: {path}")
    name_for_errors = display_name or path.name

    data = path.read_bytes()
    suffix = path.suffix.lower()

    if suffix in PLAIN_TEXT_EXTENSIONS:
        pages = _load_plain_text(data)
    elif suffix == ".pdf":
        pages = _load_pdf(data, name_for_errors)
    elif suffix == ".docx":
        pages = _load_docx(data)
    elif suffix in (".xlsx", ".xlsm"):
        pages = _load_xlsx(data)
    else:
        raise UnsupportedFileType(
            f"'{path.suffix}' isn't supported yet. FileWhisperer reads: "
            f"{', '.join(sorted(PLAIN_TEXT_EXTENSIONS))}, .pdf, .docx, .xlsx"
        )

    pages = [p for p in pages if p.text.strip()]
    if not pages:
        raise EmptyDocument(f"'{name_for_errors}' was read but contained no text.")
    return pages


def load_text(path: str | Path, display_name: str | None = None) -> str:
    """Convenience wrapper: same as load_pages() but joined into one
    string, for callers that don't care about page boundaries."""
    pages = load_pages(path, display_name)
    return "\n\n".join(p.text for p in pages)
