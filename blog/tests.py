import os
import json
import shutil
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.messages.storage.fallback import FallbackStorage
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.http import HttpRequest
from django.test import SimpleTestCase, override_settings
from django.test.client import RequestFactory
from django.urls import reverse

from blog.management.commands.add_users_content import Command as AddUsersContentCommand
from blog.views import (
    ContactsView,
    redirect_to_referer_or_detail,
    send_moderation_email,
    tinymce_image_upload,
    user_can_create_posts,
)


class AddCategoriesPagesCommandTests(SimpleTestCase):
    """Проверяет команды загрузки фикстур без обращения к базе данных."""

    @patch("blog.management.commands.add_users_content.call_command")
    def test_add_users_content_calls_loaddata(self, call_command_mock):
        command = AddUsersContentCommand()

        command.handle()

        call_command_mock.assert_called_once_with(
            "loaddata", "fixtures/users_fixtures.json"
        )


class BlogWorkflowTestCase(SimpleTestCase):
    """Проверяет прикладную логику блога без ORM и тестовой БД."""

    def setUp(self):
        self.factory = RequestFactory()

    def _build_request_with_messages(self, path, data):
        request = self.factory.post(path, data=data)
        request.session = {}
        request._messages = FallbackStorage(request)
        return request

    def test_author_can_create_posts(self):
        user = SimpleNamespace(
            is_authenticated=True,
            is_superuser=False,
            has_perm=lambda perm: False,
        )

        self.assertTrue(user_can_create_posts(user))

    def test_moderator_cannot_create_posts(self):
        user = SimpleNamespace(
            is_authenticated=True,
            is_superuser=False,
            has_perm=lambda perm: perm == "blog.can_approve_blog",
        )

        self.assertFalse(user_can_create_posts(user))

    def test_superuser_can_create_posts(self):
        user = SimpleNamespace(
            is_authenticated=True,
            is_superuser=True,
            has_perm=lambda perm: True,
        )

        self.assertTrue(user_can_create_posts(user))

    def test_redirect_to_referer_uses_previous_page(self):
        request = self.factory.get("/posts/1/", HTTP_REFERER="/users/profile/")

        response = redirect_to_referer_or_detail(request, pk=1)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/users/profile/")

    def test_redirect_to_referer_falls_back_to_detail(self):
        request = self.factory.get("/posts/1/")

        response = redirect_to_referer_or_detail(request, pk=7)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("blog:blog_detail", args=[7]))

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        DEFAULT_FROM_EMAIL="noreply@example.com",
    )
    def test_send_moderation_email_for_approved_article(self):
        blog = SimpleNamespace(
            title="Test article",
            author=SimpleNamespace(email="author@example.com"),
        )

        send_moderation_email(blog, approved=True)

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("одобрена", mail.outbox[0].subject)
        self.assertEqual(mail.outbox[0].to, ["author@example.com"])

    @override_settings(
        DEFAULT_FROM_EMAIL="site@example.com", SERVER_EMAIL="server@example.com"
    )
    @patch("blog.views.send_mail")
    def test_contacts_view_sends_message_to_admin_email(self, send_mail_mock):
        request = self._build_request_with_messages(
            reverse("blog:contacts"),
            {"name": "Иван", "email": "ivan@example.com", "message": "Привет"},
        )

        with patch.dict(os.environ, {"ADMIN_EMAIL": "admin@example.com"}, clear=False):
            response = ContactsView.as_view()(request)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("blog:contact_message"))
        send_mail_mock.assert_called_once()
        self.assertEqual(
            send_mail_mock.call_args.kwargs["recipient_list"], ["admin@example.com"]
        )


class BlogMediaRegressionTests(SimpleTestCase):
    """Проверяет загрузку изображений без участия базы данных."""

    def setUp(self):
        self.factory = RequestFactory()

    def _build_upload(self, name="sample.png", size=(1600, 900), color="cyan"):
        from PIL import Image
        import io

        image = Image.new("RGB", size, color=color)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        buffer.seek(0)
        return SimpleUploadedFile(name, buffer.read(), content_type="image/png")

    def test_tinymce_upload_creates_responsive_variants(self):
        temp_media = tempfile.mkdtemp(prefix="exam-work-media-")
        try:
            with self.settings(MEDIA_ROOT=temp_media):
                upload = self._build_upload(name="editor.png")
                request = HttpRequest()
                request.method = "POST"
                request.FILES = {"file": upload}

                response = tinymce_image_upload(request)
                payload = json.loads(response.content)
                base_name = payload["location"].split("/")[-1].rsplit(".", 1)[0]

                self.assertEqual(response.status_code, 200)
                self.assertIn("/media/blog/originals/", payload["location"])
                self.assertTrue(
                    os.path.exists(
                        os.path.join(temp_media, f"blog/desktop/{base_name}_desktop.webp")
                    )
                )
                self.assertTrue(
                    os.path.exists(
                        os.path.join(temp_media, f"blog/tablets/{base_name}_tablet.webp")
                    )
                )
                self.assertTrue(
                    os.path.exists(
                        os.path.join(temp_media, f"blog/mobile/{base_name}_mobile.webp")
                    )
                )
        finally:
            shutil.rmtree(temp_media, ignore_errors=True)

    def test_tinymce_upload_returns_400_for_invalid_request(self):
        request = HttpRequest()
        request.method = "GET"
        request.FILES = {}

        response = tinymce_image_upload(request)

        self.assertEqual(response.status_code, 400)


@override_settings(DEBUG=False)
class ProjectErrorPagesTests(SimpleTestCase):
    """Проверяет пользовательские страницы системных ошибок."""

    def test_custom_404_template_is_used(self):
        response = self.client.get("/definitely-missing-page/")

        self.assertEqual(response.status_code, 404)
        self.assertTemplateUsed(response, "404.html")
