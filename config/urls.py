from django.contrib import admin
from django.urls import path, include
from django.conf.urls.static import static
from django.conf import settings

handler404 = "config.views.custom_page_not_found"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("blog.urls", namespace="blog")),
    path("users/", include("users.urls", namespace="users")),
    path("tinymce/upload/", include("blog.tinymce_upload_urls")),
    path("tinymce/", include("tinymce.urls")),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
