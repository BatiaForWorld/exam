"""Модели блога и логика обработки изображений."""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from PIL import Image
from django.core.files.storage import default_storage

from .image_utils import build_responsive_webp_variants

Image.MAX_IMAGE_PIXELS = 20_000_000


class Category(models.Model):
    """Категория публикаций с адаптивным изображением."""

    name = models.CharField(max_length=80, unique=True, verbose_name="Категория")

    description = models.TextField(
        max_length=200, blank=True, null=True, verbose_name="Описание категории"
    )

    image = models.ImageField(upload_to="blog/originals/", blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Категория"
        verbose_name_plural = "Категории"
        ordering = ["-created_at"]

    def __str__(self):
        return self.name

    def image_variant_paths(self, image_name=None):
        """Возвращает пути к адаптивным вариантам изображения категории."""

        source_name = image_name or (self.image.name if self.image else None)
        if not source_name:
            return {}

        base_name = source_name.rsplit("/", 1)[-1].rsplit(".", 1)[0]
        return {
            "desktop": f"blog/desktop/{base_name}_desktop.webp",
            "tablet": f"blog/tablets/{base_name}_tablet.webp",
            "mobile": f"blog/mobile/{base_name}_mobile.webp",
        }

    def delete_old_images(self, image_name=None):
        """Удаляет ранее сгенерированные варианты изображения категории."""

        for path in self.image_variant_paths(image_name).values():
            try:
                default_storage.delete(path)
            except Exception:
                pass

    def clean(self):
        """Проверяет корректность изображения категории перед сохранением."""

        super().clean()

        if not self.image:
            return

        if self.pk:
            old_image = (
                Category.objects.filter(pk=self.pk)
                .values_list("image", flat=True)
                .first()
            )
            if old_image and old_image == self.image.name:
                return

        if self.image.size > 2 * 1024 * 1024:
            raise ValidationError(
                {"image": "Размер изображения не может превышать 2MB"}
            )

        try:
            img = Image.open(self.image)
            img.verify()
        except Exception:
            raise ValidationError(
                {"image": "Файл изображения повреждён или не является изображением"}
            )

    def process_image_versions(self):
        """Создаёт адаптивные WEBP-версии изображения категории."""

        if not self.image:
            return

        variants = self.image_variant_paths()
        with self.image.storage.open(self.image.name, "rb") as source_file:
            generated = build_responsive_webp_variants(
                source_file, self.image.name.rsplit("/", 1)[-1].rsplit(".", 1)[0]
            )

        for key, path in variants.items():
            if not default_storage.exists(path):
                default_storage.save(path, generated[key])

    def save(self, *args, **kwargs):
        """Сохраняет категорию и обновляет связанные изображения."""

        old_image = None
        if self.pk:
            old_image = (
                Category.objects.filter(pk=self.pk)
                .values_list("image", flat=True)
                .first()
            )

        self.full_clean()
        super().save(*args, **kwargs)

        if self.image and self.image.name != old_image:
            if old_image:
                try:
                    self.image.storage.delete(old_image)
                except Exception:
                    pass
                self.delete_old_images(old_image)
            self.process_image_versions()

    def delete(self, *args, **kwargs):
        """Удаляет категорию вместе с исходным и адаптивными изображениями."""

        if self.image and self.image.name:
            self.delete_old_images(self.image.name)
            try:
                self.image.storage.delete(self.image.name)
            except Exception:
                pass
        return super().delete(*args, **kwargs)


class Blog(models.Model):
    """Публикация дневника с превью, статусами и просмотрами."""

    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="blogs",
        verbose_name="Автор",
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="blogs",
        verbose_name="Категория",
    )
    title = models.CharField(max_length=255)
    content = models.TextField()

    preview = models.ImageField(upload_to="blog/originals/", blank=True, null=True)

    preview_mobile = models.ImageField(upload_to="blog/mobile/", blank=True, null=True)
    preview_tablet = models.ImageField(upload_to="blog/tablets/", blank=True, null=True)
    preview_desktop = models.ImageField(
        upload_to="blog/desktop/", blank=True, null=True
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_published = models.BooleanField(default=False)
    is_approved = models.BooleanField(default=False)
    views_count = models.PositiveIntegerField(default=0)

    MAX_FILE_SIZE = 2 * 1024 * 1024
    ALLOWED_FORMATS = ["JPEG", "PNG", "WEBP"]
    MAX_RESOLUTION = (2000, 2000)

    class Meta:
        ordering = ["-created_at"]
        permissions = [
            ("can_approve_blog", "Can approve blog"),
        ]

    def delete_old_previews(self):
        """Удаляет ранее созданные адаптивные превью записи."""

        for field_name in ["preview_desktop", "preview_tablet", "preview_mobile"]:
            field_file = getattr(self, field_name)
            if field_file and field_file.name:
                try:
                    field_file.delete(save=False)
                except Exception:
                    pass

    def clean(self):
        """Проверяет превью записи на размер, формат и целостность."""

        super().clean()

        if not self.preview:
            return

        if self.pk:
            old_preview = (
                Blog.objects.filter(pk=self.pk)
                .values_list("preview", flat=True)
                .first()
            )
            if old_preview and old_preview == self.preview.name:
                return

        if self.preview.size > self.MAX_FILE_SIZE:
            raise ValidationError({"preview": "Размер превью не может превышать 2MB"})

        try:
            img = Image.open(self.preview)
            img.verify()
        except Exception:
            raise ValidationError(
                {"preview": "Файл превью повреждён или не является изображением"}
            )

        img = Image.open(self.preview)
        if img.format not in self.ALLOWED_FORMATS:
            raise ValidationError(
                {"preview": f"Допустимые форматы: {', '.join(self.ALLOWED_FORMATS)}"}
            )

        if img.width > self.MAX_RESOLUTION[0] or img.height > self.MAX_RESOLUTION[1]:
            raise ValidationError(
                {"preview": "Слишком большое разрешение (макс 2000x2000)"}
            )

    def process_preview_images(self):
        """Создаёт адаптивные WEBP-версии превью публикации."""

        if not self.preview:
            return

        self.delete_old_previews()

        base_name = self.preview.name.rsplit("/", 1)[-1].rsplit(".", 1)[0]

        variants = build_responsive_webp_variants(self.preview, base_name)

        self.preview_desktop.save(
            variants["desktop"].name, variants["desktop"], save=False
        )
        self.preview_tablet.save(
            variants["tablet"].name, variants["tablet"], save=False
        )
        self.preview_mobile.save(
            variants["mobile"].name, variants["mobile"], save=False
        )

        super().save(
            update_fields=["preview_desktop", "preview_tablet", "preview_mobile"]
        )

    def save(self, *args, **kwargs):
        """Сохраняет публикацию и обновляет связанные превью."""

        old_preview = None
        if self.pk:
            old_preview = (
                Blog.objects.filter(pk=self.pk)
                .values_list("preview", flat=True)
                .first()
            )

        self.full_clean()
        super().save(*args, **kwargs)

        if self.preview and self.preview != old_preview:
            if old_preview:
                try:
                    self.preview.storage.delete(old_preview)
                except Exception:
                    pass
            self.process_preview_images()

    def delete(self, *args, **kwargs):
        """Удаляет публикацию вместе со всеми файлами превью."""

        for field_name in [
            "preview",
            "preview_desktop",
            "preview_tablet",
            "preview_mobile",
        ]:
            field_file = getattr(self, field_name)
            if field_file and field_file.name:
                try:
                    field_file.storage.delete(field_file.name)
                except Exception:
                    pass
        return super().delete(*args, **kwargs)

    def __str__(self):
        return self.title
