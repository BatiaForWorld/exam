from io import BytesIO

from django.core.files.base import ContentFile
from PIL import Image

RESPONSIVE_SIZES = {
    "desktop": (1200, 630),
    "tablet": (800, 420),
    "mobile": (480, 250),
}


def build_responsive_webp_variants(source_file, base_name):
    source_file.seek(0)
    image = Image.open(source_file)

    if image.mode != "RGB":
        image = image.convert("RGB")

    resample = getattr(Image, "LANCZOS", Image.BICUBIC)
    variants = {}

    for key, size in RESPONSIVE_SIZES.items():
        img_copy = image.copy()
        img_copy.thumbnail(size, resample)

        buffer = BytesIO()
        img_copy.save(buffer, format="WEBP", quality=85)
        buffer.seek(0)

        file_name = f"{base_name}_{key}.webp"
        variants[key] = ContentFile(buffer.read(), name=file_name)

    return variants
