from django.urls import path
from blog.apps import BlogConfig
from blog.views import (
    IndexListView,
    BlogCreateView,
    BlogUpdateView,
    BlogDeleteView,
    BlogDetailView,
    ContactsView,
    ContactMessageView,
    BlogListView,
    BlogTogglePublishView,
    BlogRejectView,
    BlogSubmitForReviewView,
    CategoryListView,
)
from django.conf import settings
from django.conf.urls.static import static

app_name = BlogConfig.name

urlpatterns = [
    path("", IndexListView.as_view(), name="index"),
    path("categories/", CategoryListView.as_view(), name="categories"),
    path("list/", BlogListView.as_view(), name="blog_list"),
    path("blog_list/", BlogListView.as_view(), name="blog_list"),
    path("create/", BlogCreateView.as_view(), name="blog_create"),
    path("create", BlogCreateView.as_view(), name="blog_create"),
    path("<int:pk>/", BlogDetailView.as_view(), name="blog_detail"),
    path("<int:pk>/update/", BlogUpdateView.as_view(), name="blog_update"),
    path("<int:pk>/delete/", BlogDeleteView.as_view(), name="blog_delete"),
    path(
        "<int:pk>/toggle-publish/",
        BlogTogglePublishView.as_view(),
        name="blog_toggle_publish",
    ),
    path(
        "<int:pk>/submit/",
        BlogSubmitForReviewView.as_view(),
        name="blog_submit_for_review",
    ),
    path("<int:pk>/reject/", BlogRejectView.as_view(), name="blog_reject"),
    path("contacts/", ContactsView.as_view(), name="contacts"),
    path("contacts", ContactsView.as_view(), name="contacts"),
    path("contact_message/", ContactMessageView.as_view(), name="contact_message"),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
