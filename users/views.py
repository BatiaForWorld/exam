"""Views приложения пользователей: регистрация, профиль и восстановление доступа."""

from django.contrib.auth.views import (
    LoginView,
    PasswordChangeView,
    PasswordChangeDoneView,
    PasswordResetView,
    PasswordResetDoneView,
    PasswordResetConfirmView,
    PasswordResetCompleteView,
)
from django.core.mail import send_mail
from django.views import View
from django.contrib.auth import logout
from django.views.decorators.csrf import csrf_protect
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView, CreateView
from .models import User
from blog.models import Blog
from django.shortcuts import get_object_or_404, redirect, reverse
from django.urls import reverse_lazy
from config.settings import EMAIL_HOST_USER
from users.forms import (
    UserRegisterForm,
    LoginForm,
    CustomPasswordChangeForm,
    CustomPasswordResetForm,
    CustomSetPasswordForm,
    UserProfileForm,
    UserAvatarForm,
)
from django.utils.decorators import method_decorator
from django.http import HttpResponseNotAllowed
import secrets
from django.views.generic.edit import UpdateView


class RegisterView(CreateView):
    """Регистрирует пользователя и отправляет письмо для подтверждения email."""

    template_name = "users/register.html"
    form_class = UserRegisterForm
    success_url = reverse_lazy("users:login")

    def form_valid(self, form):
        self.object = form.save(commit=False)
        self.object.is_active = False
        token = secrets.token_hex(16)
        self.object.token = token
        self.object.save()
        host = self.request.get_host()
        url = f"http://{host}/users/email-confirm/{token}/"
        send_mail(
            subject="Подтверждение почты",
            message=f"Здравствуйте! Вы зарегистрировались на сайте ведения дневника,"
                    f" перейдите по ссылке для подтверждения почты {url}",
            from_email=EMAIL_HOST_USER,
            recipient_list=[self.object.email],
        )
        return redirect(self.get_success_url())


def email_verification(request, token):
    """Активирует пользователя по токену подтверждения."""

    user = get_object_or_404(User, token=token)
    user.is_active = True
    user.token = None
    user.save(update_fields=["is_active", "token"])
    return redirect(reverse("users:login"))


class UserLoginView(LoginView):
    """Отображает форму входа по email."""

    template_name = "users/login.html"
    authentication_form = LoginForm


class ProfileView(LoginRequiredMixin, TemplateView):
    """Показывает профиль пользователя, его статьи и очередь модерации."""

    template_name = "users/profile.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        posts = user.blogs.all().order_by("-created_at")

        status = self.request.GET.get("status", "all")
        if status == "published":
            list_posts = posts.filter(is_published=True)
        elif status == "draft":
            list_posts = posts.filter(is_published=False)
        else:
            list_posts = posts

        context["user"] = user
        context["my_posts"] = list_posts
        context["posts_total"] = posts.count()
        context["posts_published"] = posts.filter(
            is_published=True, is_approved=True
        ).count()
        context["posts_draft"] = posts.filter(
            is_published=False, is_approved=False
        ).count()
        context["posts_on_review"] = posts.filter(
            is_published=True, is_approved=False
        ).count()
        context["status"] = status

        if user.has_perm("blog.can_approve_blog") or user.is_superuser:
            context["moderation_posts"] = Blog.objects.filter(
                is_published=True,
                is_approved=False,
            ).order_by("-created_at")
        else:
            context["moderation_posts"] = Blog.objects.none()

        return context


class ProfileEditView(LoginRequiredMixin, UpdateView):
    """Редактирует основные данные профиля текущего пользователя."""

    model = User
    form_class = UserProfileForm
    template_name = "users/profile_edit.html"
    success_url = reverse_lazy("users:profile")

    def get_object(self, queryset=None):
        return self.request.user


class AvatarChangeView(LoginRequiredMixin, UpdateView):
    """Позволяет пользователю сменить аватар."""

    model = User
    form_class = UserAvatarForm
    template_name = "users/avatar_change.html"
    success_url = reverse_lazy("users:profile")

    def get_object(self, queryset=None):
        return self.request.user


class CustomPasswordChangeView(LoginRequiredMixin, PasswordChangeView):
    """Меняет пароль авторизованного пользователя."""

    template_name = "users/password_change_form.html"
    form_class = CustomPasswordChangeForm
    success_url = reverse_lazy("users:password_change_done")


class CustomPasswordChangeDoneView(LoginRequiredMixin, PasswordChangeDoneView):
    """Показывает сообщение об успешной смене пароля."""

    template_name = "users/password_change_done.html"


class CustomPasswordResetView(PasswordResetView):
    """Запускает восстановление пароля по email."""

    template_name = "users/password_reset_form.html"
    email_template_name = "users/password_reset_email.html"
    form_class = CustomPasswordResetForm
    success_url = reverse_lazy("users:password_reset_done")


class CustomPasswordResetDoneView(PasswordResetDoneView):
    """Подтверждает отправку письма для восстановления пароля."""

    template_name = "users/password_reset_done.html"


class CustomPasswordResetConfirmView(PasswordResetConfirmView):
    """Позволяет задать новый пароль по токену из письма."""

    template_name = "users/password_reset_confirm.html"
    form_class = CustomSetPasswordForm
    success_url = reverse_lazy("users:password_reset_complete")


class CustomPasswordResetCompleteView(PasswordResetCompleteView):
    """Показывает финальную страницу успешного сброса пароля."""

    template_name = "users/password_reset_complete.html"


@method_decorator(csrf_protect, name="dispatch")
class CustomLogoutView(View):
    """Разрешает выход из системы только через POST-запрос."""

    def post(self, request, *args, **kwargs):
        logout(request)
        return redirect(reverse_lazy("users:logged_out"))

    def get(self, request, *args, **kwargs):
        return HttpResponseNotAllowed(["POST"])
