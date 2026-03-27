from django.urls import path
from django.views.generic import TemplateView
from users.apps import UsersConfig
from users.views import (
    RegisterView,
    CustomLogoutView,
    UserLoginView,
    ProfileView,
    ProfileEditView,
    AvatarChangeView,
    CustomPasswordChangeView,
    CustomPasswordChangeDoneView,
    CustomPasswordResetView,
    CustomPasswordResetDoneView,
    CustomPasswordResetConfirmView,
    CustomPasswordResetCompleteView,
    email_verification,
)

app_name = UsersConfig.name

urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path(
        "login/", UserLoginView.as_view(template_name="users/login.html"), name="login"
    ),
    path("logout/", CustomLogoutView.as_view(), name="logout"),
    path(
        "logged_out/",
        TemplateView.as_view(template_name="users/logged_out.html"),
        name="logged_out",
    ),
    path("profile/", ProfileView.as_view(), name="profile"),
    path("profile/edit/", ProfileEditView.as_view(), name="profile_edit"),
    path("profile/avatar/", AvatarChangeView.as_view(), name="avatar_change"),
    path(
        "password_change/", CustomPasswordChangeView.as_view(), name="password_change"
    ),
    path(
        "password_change/done/",
        CustomPasswordChangeDoneView.as_view(),
        name="password_change_done",
    ),
    path("password_reset/", CustomPasswordResetView.as_view(), name="password_reset"),
    path(
        "password_reset/done/",
        CustomPasswordResetDoneView.as_view(),
        name="password_reset_done",
    ),
    path(
        "reset/<uidb64>/<token>/",
        CustomPasswordResetConfirmView.as_view(),
        name="password_reset_confirm",
    ),
    path(
        "reset/done/",
        CustomPasswordResetCompleteView.as_view(),
        name="password_reset_complete",
    ),
    path("email-confirm/<str:token>/", email_verification, name="email-confirm"),
]
