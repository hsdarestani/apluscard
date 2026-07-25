from PIL import Image, ImageOps
from django.conf import settings


BRAND_ICON_RELATIVE_PATH = ("mobile", "assets", "icon-only.png")
BRAND_ASSET_VERSION = "scl-20260725"


def load_brand_icon(size):
    """Load the exact store/native icon and resize it without redesigning it."""
    path = settings.BASE_DIR.joinpath(*BRAND_ICON_RELATIVE_PATH)
    try:
        with Image.open(path) as source:
            return ImageOps.fit(
                source.convert("RGBA"),
                (size, size),
                method=Image.Resampling.LANCZOS,
                centering=(0.5, 0.5),
            )
    except (FileNotFoundError, OSError):
        return None
