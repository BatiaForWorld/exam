from django.urls import path
from .views import tinymce_image_upload

urlpatterns = [
    path("", tinymce_image_upload, name="tinymce_image_upload"),
]
