"""Модели пользователей и логика обработки аватаров."""

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.core.exceptions import ValidationError
from django.db import models
from django.core.files.base import ContentFile
import os
from io import BytesIO
from PIL import Image


class CustomUserManager(BaseUserManager):
    """Менеджер для кастомной модели пользователя с авторизацией по email."""

    use_in_migrations = True

    def create_user(self, email, password=None, **extra_fields):
        """Создаёт обычного пользователя."""

        if not email:
            raise ValueError("Пользователю требуется email")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        """Создаёт суперпользователя с обязательными флагами доступа."""

        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Суперпользователь должен иметь is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Суперпользователь должен иметь is_superuser=True.")

        return self.create_user(email, password, **extra_fields)


class User(AbstractUser):
    """Кастомный пользователь с профилем и адаптивными аватарами."""

    username = None

    email = models.EmailField(unique=True)

    phone = models.CharField(
        max_length=35,
        verbose_name="Телефон",
        blank=True,
        null=True,
        help_text="Введите номер телефона",
    )

    avatar = models.ImageField(
        upload_to="users/avatar/original/",
        blank=True,
        null=True,
        help_text="Загрузите аватар",
    )

    avatar_mobile = models.ImageField(
        upload_to="users/avatar/mobile/", blank=True, null=True
    )
    avatar_tablet = models.ImageField(
        upload_to="users/avatar/tablets/", blank=True, null=True
    )
    avatar_desktop = models.ImageField(
        upload_to="users/avatar/desktop/", blank=True, null=True
    )

    country = models.CharField(
        max_length=35,
        verbose_name="Страна",
        blank=True,
        null=True,
        help_text="Укажите вашу страну",
    )
    token = models.CharField(
        max_length=100, verbose_name="Token", blank=True, null=True
    )

    objects = CustomUserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    MAX_FILE_SIZE = 2 * 1024 * 1024
    ALLOWED_FORMATS = ["JPEG", "PNG", "WEBP"]

    def __str__(self):
        return self.email

    def process_avatar(self):
        """Создаёт адаптивные WEBP-версии загруженного аватара."""

        sizes = {
            "desktop": (324, 324),
            "tablet": (212, 212),
            "mobile": (106, 106),
        }

        img = Image.open(self.avatar)

        if img.mode != "RGB":
            img = img.convert("RGB")

        filename = os.path.splitext(os.path.basename(self.avatar.name))[0]

        self.delete_old_avatars()

        for field, size in sizes.items():
            resized = img.copy()
            resized.thumbnail(size)

            buffer = BytesIO()
            resized.save(buffer, format="WEBP", quality=85)

            file_name = f"{filename}_{field}.webp"
            django_file = ContentFile(buffer.getvalue(), name=file_name)

            if field == "desktop":
                self.avatar_desktop.save(file_name, django_file, save=False)
            elif field == "tablet":
                self.avatar_tablet.save(file_name, django_file, save=False)
            elif field == "mobile":
                self.avatar_mobile.save(file_name, django_file, save=False)

        User.objects.filter(pk=self.pk).update(
            avatar_desktop=self.avatar_desktop,
            avatar_tablet=self.avatar_tablet,
            avatar_mobile=self.avatar_mobile,
        )

    def clean(self):
        """Проверяет загруженный аватар перед сохранением."""

        super().clean()

        if not self.avatar:
            return

        if self.pk:
            old_avatar = (
                User.objects.filter(pk=self.pk).values_list("avatar", flat=True).first()
            )
            if old_avatar and old_avatar == self.avatar.name:
                return

        if self.avatar.size > self.MAX_FILE_SIZE:
            raise ValidationError({"avatar": "Размер аватара не может превышать 2MB"})

        try:
            img = Image.open(self.avatar)
            img.verify()
        except Exception:
            raise ValidationError(
                {"avatar": "Файл не является корректным изображением"}
            )

        img = Image.open(self.avatar)
        if img.format not in self.ALLOWED_FORMATS:
            raise ValidationError(
                {"avatar": f"Допустимые форматы: {', '.join(self.ALLOWED_FORMATS)}"}
            )

    def delete_old_avatars(self):
        """Удаляет ранее сгенерированные файлы аватара."""

        for field in ["avatar_desktop", "avatar_tablet", "avatar_mobile"]:
            file = getattr(self, field)
            if file and file.name:
                try:
                    file.storage.delete(file.name)
                except Exception:
                    pass

    def save(self, *args, **kwargs):
        """Сохраняет пользователя и обновляет адаптивные аватары."""

        old_avatar = None
        if self.pk:
            old_avatar = (
                User.objects.filter(pk=self.pk).values_list("avatar", flat=True).first()
            )

        self.full_clean(exclude=["password"])
        super().save(*args, **kwargs)

        if self.avatar and self.avatar.name != old_avatar:
            if old_avatar:
                try:
                    self.avatar.storage.delete(old_avatar)
                except Exception:
                    pass
            self.delete_old_avatars()
            self.process_avatar()

    def delete(self, *args, **kwargs):
        """Удаляет пользователя вместе с файлами аватара."""

        for field in ["avatar", "avatar_desktop", "avatar_tablet", "avatar_mobile"]:
            file = getattr(self, field)
            if file and file.name:
                try:
                    file.storage.delete(file.name)
                except Exception:
                    pass
        return super().delete(*args, **kwargs)

    class Meta:
        verbose_name = "Пользователь"
        verbose_name_plural = "Пользователи"
