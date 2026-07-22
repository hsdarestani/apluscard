import base64
from io import BytesIO

import qrcode


def qr_png_bytes(value, *, box_size=8, border=2):
    code = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=box_size,
        border=border,
    )
    code.add_data(str(value))
    code.make(fit=True)
    image = code.make_image(fill_color="black", back_color="white")
    output = BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()


def qr_data_uri(value, *, box_size=8, border=2):
    encoded = base64.b64encode(qr_png_bytes(value, box_size=box_size, border=border)).decode("ascii")
    return f"data:image/png;base64,{encoded}"
