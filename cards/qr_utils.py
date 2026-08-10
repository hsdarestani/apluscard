import base64
from io import BytesIO

import qrcode
from qrcode.image.svg import SvgPathImage


DEFAULT_ERROR_CORRECTION = qrcode.constants.ERROR_CORRECT_M
DEFAULT_BORDER = 4


def _build_qr(value, *, box_size=8, border=DEFAULT_BORDER):
    code = qrcode.QRCode(
        version=None,
        error_correction=DEFAULT_ERROR_CORRECTION,
        box_size=box_size,
        border=border,
    )
    code.add_data(str(value))
    code.make(fit=True)
    return code


def qr_png_bytes(value, *, box_size=8, border=DEFAULT_BORDER):
    code = _build_qr(value, box_size=box_size, border=border)
    image = code.make_image(fill_color="black", back_color="white")
    output = BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()


def qr_svg_bytes(value, *, border=DEFAULT_BORDER):
    """Return a crisp vector QR image for phone-to-phone scanning.

    The customer card is frequently scanned from another phone screen. SVG avoids
    bitmap resampling in Android WebView/WKWebView, while the four-module quiet
    zone and medium error correction keep the symbol less dense and easier for
    older or lower-quality cameras to lock onto.
    """

    code = _build_qr(value, box_size=10, border=border)
    image = code.make_image(image_factory=SvgPathImage)
    output = BytesIO()
    image.save(output)
    return output.getvalue()


def qr_data_uri(value, *, box_size=8, border=DEFAULT_BORDER):
    encoded = base64.b64encode(qr_png_bytes(value, box_size=box_size, border=border)).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def qr_svg_data_uri(value, *, border=DEFAULT_BORDER):
    encoded = base64.b64encode(qr_svg_bytes(value, border=border)).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"
