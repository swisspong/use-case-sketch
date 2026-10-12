"""PageRenderer port with real pypdfium2 rasterization and Pillow decoding."""

from io import BytesIO

from PIL import Image
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, NameObject
import pytest

from contexts.document_processing.v3.application.use_cases.ocr_document_pages.errors import PageRenderingError
from contexts.document_processing.v3.infrastructure.pypdfium2_page_renderer import Pypdfium2PageRenderer


def pdf_with(*pages):
    """pages: (width_pt, height_pt, content_stream) in document order."""
    writer = PdfWriter()
    for width, height, content in pages:
        page = writer.add_blank_page(width=width, height=height)
        stream = DecodedStreamObject()
        stream.set_data(content)
        page[NameObject("/Contents")] = writer._add_object(stream)
    with BytesIO() as buffer:
        writer.write(buffer)
        return buffer.getvalue()


LEFT_HALF_BLACK = b"0 0 0 rg 0 0 150 100 re f"


def decode(image):
    assert image.media_type == "image/png"
    assert image.data.startswith(b"\x89PNG\r\n\x1a\n")
    return Image.open(BytesIO(image.data))


def test_only_the_requested_page_is_rasterized_at_the_configured_resolution():
    pdf = pdf_with((100, 200, b""), (300, 100, LEFT_HALF_BLACK))

    picture = decode(Pypdfium2PageRenderer(dpi=144, max_side_pixels=4000).render(pdf=pdf, page_number=2))

    assert picture.size == (600, 200)  # 300x100 pt at 2x, not page 1's 100x200
    grey = picture.convert("L")
    assert grey.getpixel((100, 100)) < 30
    assert grey.getpixel((500, 100)) > 225


def test_large_pages_are_bounded_by_the_longest_side():
    pdf = pdf_with((5000, 2500, b""))

    picture = decode(Pypdfium2PageRenderer(dpi=144, max_side_pixels=2000).render(pdf=pdf, page_number=1))

    assert max(picture.size) <= 2000
    assert picture.size[0] >= 1999 and abs(picture.size[0] / picture.size[1] - 2) < 0.01


@pytest.mark.parametrize("pdf,page_number", [
    (b"not a pdf", 1),
    (b"%PDF-1.7 truncated", 1),
    (pdf_with((100, 100, b"")), 2),
])
def test_unrenderable_input_is_a_page_rendering_error(pdf, page_number):
    with pytest.raises(PageRenderingError) as caught:
        Pypdfium2PageRenderer().render(pdf=pdf, page_number=page_number)

    assert str(caught.value) == "Page rendering unavailable"


@pytest.mark.parametrize("settings", [
    {"dpi": 0}, {"dpi": 1201}, {"dpi": float("nan")}, {"max_side_pixels": 0}, {"max_side_pixels": 1.5},
])
def test_invalid_render_limits_are_rejected_at_construction(settings):
    with pytest.raises(ValueError):
        Pypdfium2PageRenderer(**settings)
