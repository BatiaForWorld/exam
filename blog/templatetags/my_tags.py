from django import template
from django.conf import settings
from django.core.files.storage import default_storage
from django.utils.safestring import mark_safe
import os
import re

register = template.Library()


@register.filter()
def media_filter(path):
    if not path:
        return "#"
    if hasattr(path, "url"):
        return path.url
    if path.startswith("http"):
        return path
    return f"{settings.MEDIA_URL}{path}"


@register.simple_tag
def responsive_picture(
    post, alt_text="", classes="card-img-top", style="height: 180px; object-fit: cover;"
):
    src_default = None
    if getattr(post, "preview_mobile", None):
        src_default = media_filter(post.preview_mobile)
    elif getattr(post, "preview_tablet", None):
        src_default = media_filter(post.preview_tablet)
    elif getattr(post, "preview_desktop", None):
        src_default = media_filter(post.preview_desktop)
    elif getattr(post, "preview", None):
        src_default = media_filter(post.preview)

    if not src_default:
        return ""

    lines = ["<picture>"]
    if getattr(post, "preview_desktop", None):
        lines.append(
            f'<source type="image/webp" media="(min-width: 1200px)" srcset="{media_filter(post.preview_desktop)}">'
        )
    if getattr(post, "preview_tablet", None):
        lines.append(
            f'<source type="image/webp" media="(min-width: 768px)" srcset="{media_filter(post.preview_tablet)}">'
        )
    if getattr(post, "preview_mobile", None):
        lines.append(
            f'<source type="image/webp" media="(max-width: 767px)" srcset="{media_filter(post.preview_mobile)}">'
        )
    if getattr(post, "preview_desktop", None):
        img_fallback = media_filter(post.preview_desktop)
    elif getattr(post, "preview_tablet", None):
        img_fallback = media_filter(post.preview_tablet)
    elif getattr(post, "preview_mobile", None):
        img_fallback = media_filter(post.preview_mobile)
    else:
        img_fallback = src_default

    lines.append(
        f'<img src="{img_fallback}" class="{classes} img-fluid" style="{style}" alt="{alt_text}">'
    )
    lines.append("</picture>")
    return mark_safe("".join(lines))


@register.simple_tag
def responsive_category_picture(
    category, alt_text="", classes="img-fluid", style="max-width: 220px;"
):
    if not getattr(category, "image", None):
        return ""

    base_name = category.image.name.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    desktop_path = f"blog/desktop/{base_name}_desktop.webp"
    tablet_path = f"blog/tablets/{base_name}_tablet.webp"
    mobile_path = f"blog/mobile/{base_name}_mobile.webp"

    desktop_exists = default_storage.exists(desktop_path)
    tablet_exists = default_storage.exists(tablet_path)
    mobile_exists = default_storage.exists(mobile_path)

    if mobile_exists:
        fallback = default_storage.url(mobile_path)
    elif tablet_exists:
        fallback = default_storage.url(tablet_path)
    elif desktop_exists:
        fallback = default_storage.url(desktop_path)
    else:
        fallback = media_filter(category.image)

    lines = ["<picture>"]
    if desktop_exists:
        lines.append(
            f'<source type="image/webp" media="(min-width: 1200px)" srcset="{default_storage.url(desktop_path)}">'
        )
    if tablet_exists:
        lines.append(
            f'<source type="image/webp" media="(min-width: 768px)" srcset="{default_storage.url(tablet_path)}">'
        )
    if mobile_exists:
        lines.append(
            f'<source type="image/webp" media="(max-width: 767px)" srcset="{default_storage.url(mobile_path)}">'
        )

    lines.append(
        f'<img src="{fallback}" class="{classes}" style="{style}" alt="{alt_text}">'
    )
    lines.append("</picture>")
    return mark_safe("".join(lines))


@register.filter()
def responsive_content_images(html):
    if not html:
        return html

    def replace_img(match):
        tag = match.group(0)
        src_match = re.search(r'src=["\']([^"\']+)["\']', tag)
        if not src_match:
            return tag

        src = src_match.group(1)
        if not src.startswith(settings.MEDIA_URL):
            return tag

        relative_path = src[len(settings.MEDIA_URL) :].lstrip("/")
        if not relative_path.startswith("blog/originals/"):
            return tag

        filename = os.path.basename(relative_path)
        base_name = os.path.splitext(filename)[0]
        desktop_path = f"blog/desktop/{base_name}_desktop.webp"
        tablet_path = f"blog/tablets/{base_name}_tablet.webp"
        mobile_path = f"blog/mobile/{base_name}_mobile.webp"

        if not any(
            default_storage.exists(path)
            for path in [desktop_path, tablet_path, mobile_path]
        ):
            return tag

        alt_match = re.search(r'alt=["\']([^"\']*)["\']', tag)
        alt_text = alt_match.group(1) if alt_match else ""

        picture_lines = ["<picture>"]
        if default_storage.exists(desktop_path):
            picture_lines.append(
                f'<source type="image/webp" media="(min-width: 1200px)" srcset="{default_storage.url(desktop_path)}">'
            )
        if default_storage.exists(tablet_path):
            picture_lines.append(
                f'<source type="image/webp" media="(min-width: 768px)" srcset="{default_storage.url(tablet_path)}">'
            )
        if default_storage.exists(mobile_path):
            picture_lines.append(
                f'<source type="image/webp" media="(max-width: 767px)" srcset="{default_storage.url(mobile_path)}">'
            )

        fallback_src = (
            default_storage.url(mobile_path)
            if default_storage.exists(mobile_path)
            else src
        )
        picture_lines.append(f'<img src="{fallback_src}" alt="{alt_text}">')
        picture_lines.append("</picture>")
        return "".join(picture_lines)

    converted = re.sub(r"<img\b[^>]*>", replace_img, html, flags=re.IGNORECASE)
    return mark_safe(converted)
