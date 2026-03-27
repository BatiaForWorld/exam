from django.contrib import admin
from blog.models import Blog, Category


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "description", "image", "created_at", "updated_at")
    search_fields = ("name", "description")
    readonly_fields = ("created_at", "updated_at")
    fields = ("name", "description", "image", "created_at", "updated_at")


@admin.register(Blog)
class BlogAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "title",
        "author",
        "category",
        "is_published",
        "is_approved",
        "views_count",
        "created_at",
        "updated_at",
    ]
    list_filter = (
        "author",
        "category",
        "is_published",
        "is_approved",
        "created_at",
    )
    search_fields = (
        "id",
        "title",
        "content",
        "author__email",
        "views_count",
    )
    readonly_fields = ("created_at", "updated_at")
    fields = (
        "author",
        "category",
        "title",
        "content",
        "preview",
        "is_published",
        "is_approved",
        "views_count",
        "created_at",
        "updated_at",
    )
