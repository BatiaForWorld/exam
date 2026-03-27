import os
from unittest.mock import Mock, patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command, CommandError
from django.http import HttpResponseRedirect
from django.test import RequestFactory, SimpleTestCase
from django.urls import reverse

from users.forms import LoginForm, UserAvatarForm, UserRegisterForm
from users.management.commands.csu import Command as CsuCommand
from users.views import CustomLogoutView, RegisterView, email_verification


class UserAuthTests(SimpleTestCase):
    """Проверяет формы и auth-логику без обращения к базе данных."""

    def setUp(self):
        self.factory = RequestFactory()

    def test_login_form_contains_custom_error_message(self):
        form = LoginForm()

        self.assertIn(
            "Введите правильный email и пароль", form.error_messages["invalid_login"]
        )

    def test_login_form_sets_email_placeholder(self):
        form = LoginForm()

        self.assertEqual(
            form.fields["username"].widget.attrs["placeholder"],
            "Введите ваш email",
        )

    def test_avatar_upload_validation_rejects_large_file(self):
        file = SimpleUploadedFile(
            "avatar.png",
            b"x" * (2 * 1024 * 1024 + 1),
            content_type="image/png",
        )
        form = UserAvatarForm()
        form.cleaned_data = {"avatar": file}

        with self.assertRaisesMessage(Exception, "Размер аватара не может превышать 2MB."):
            form.clean_avatar()

    def test_register_form_rejects_temporary_email(self):
        form = UserRegisterForm()
        form.cleaned_data = {"email": "temp@mailinator.com"}

        with self.assertRaisesMessage(Exception, "Использование временных email запрещено."):
            form.clean_email()

    def test_register_form_rejects_invalid_phone(self):
        form = UserRegisterForm()
        form.cleaned_data = {"phone": "abc"}

        with self.assertRaisesMessage(
            Exception, "Введите корректный номер телефона, например +71234567890"
        ):
            form.clean_phone()

    def test_logout_get_is_not_allowed(self):
        request = self.factory.get(reverse("users:logout"))

        response = CustomLogoutView.as_view()(request)

        self.assertEqual(response.status_code, 405)


class LoginFormTest(SimpleTestCase):
    """Проверяет UI-настройки формы входа без аутентификации через БД."""

    def test_login_form_has_password_placeholder(self):
        form = LoginForm()

        self.assertEqual(
            form.fields["password"].widget.attrs["placeholder"],
            "Введите пароль",
        )


class RegistrationFlowTests(SimpleTestCase):
    """Проверяет регистрацию и подтверждение email без ORM."""

    def setUp(self):
        self.factory = RequestFactory()

    @patch("users.views.send_mail")
    @patch("users.views.secrets.token_hex", return_value="token123")
    def test_registration_creates_inactive_user_and_sends_email(
        self, token_mock, send_mail_mock
    ):
        request = self.factory.post(reverse("users:register"), HTTP_HOST="testserver")
        view = RegisterView()
        view.setup(request)
        fake_user = Mock(email="new@example.com")
        fake_form = Mock()
        fake_form.save.return_value = fake_user

        response = view.form_valid(fake_form)

        fake_form.save.assert_called_once_with(commit=False)
        self.assertFalse(fake_user.is_active)
        self.assertEqual(fake_user.token, "token123")
        fake_user.save.assert_called_once()
        send_mail_mock.assert_called_once()
        self.assertIsInstance(response, HttpResponseRedirect)
        self.assertEqual(response.url, reverse("users:login"))

    @patch("users.views.redirect")
    @patch("users.views.get_object_or_404")
    def test_email_confirmation_activates_user_and_clears_token(
        self, get_object_mock, redirect_mock
    ):
        request = self.factory.get("/users/email-confirm/token123/")
        user = Mock(is_active=False, token="token123")
        get_object_mock.return_value = user
        redirect_mock.return_value = HttpResponseRedirect(reverse("users:login"))

        response = email_verification(request, "token123")

        self.assertTrue(user.is_active)
        self.assertIsNone(user.token)
        user.save.assert_called_once_with(update_fields=["is_active", "token"])
        self.assertEqual(response.status_code, 302)


class CsuCommandTests(SimpleTestCase):
    """Проверяет команду создания администратора без реальной БД."""

    @patch("users.management.commands.csu.User.objects.get_or_create")
    def test_csu_creates_or_updates_admin(self, get_or_create_mock):
        fake_user = Mock()
        get_or_create_mock.return_value = (fake_user, True)

        with patch.dict(
            os.environ,
            {"ADMIN_EMAIL": "admin@example.com", "ADMIN_PASSWORD": "AdminPass123!"},
            clear=False,
        ):
            call_command("csu")

        get_or_create_mock.assert_called_once_with(email="admin@example.com")
        fake_user.set_password.assert_called_once_with("AdminPass123!")
        self.assertTrue(fake_user.is_active)
        self.assertTrue(fake_user.is_staff)
        self.assertTrue(fake_user.is_superuser)
        fake_user.save.assert_called_once()

    def test_csu_requires_env_values(self):
        with patch.dict(
            os.environ, {"ADMIN_EMAIL": "", "ADMIN_PASSWORD": ""}, clear=False
        ):
            with self.assertRaises(CommandError):
                CsuCommand().handle()
