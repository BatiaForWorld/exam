import os
from io import BytesIO
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse_lazy, reverse
from django.views import View
from django.views.decorators.cache import cache_page
from django.views.generic import (
    ListView,
    TemplateView,
    DeleteView,
    UpdateView,
    CreateView,
    DetailView,
)

from django.db.models import Q, F
from django.conf import settings
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.core.mail import send_mail
from django.contrib import messages
from blog.models import Blog, Category
from .image_utils import build_responsive_webp_variants
from .forms import BlogForm, ContactForm
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin


def cache_page_for_anonymous(timeout):
    """Кэширует ответ только для анонимных пользователей."""

    def decorator(view_func):
        cached = cache_page(timeout)(view_func)

        def _wrapped(request, *args, **kwargs):
            if request.user.is_authenticated:
                return view_func(request, *args, **kwargs)
            return cached(request, *args, **kwargs)

        return _wrapped

    return decorator


def user_can_create_posts(user):
    """Возвращает `True`, если пользователю разрешено создавать статьи."""

    return user.is_authenticated and (
        user.is_superuser or not user.has_perm("blog.can_approve_blog")
    )


class AuthorRoleRequiredMixin(UserPassesTestMixin):
    """Ограничивает создание статей для модераторов."""

    def test_func(self):
        return user_can_create_posts(self.request.user)


class IndexListView(TemplateView):
    """Отображает главную страницу с категориями и последними публикациями."""

    template_name = "blog/index.html"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return super().dispatch(request, *args, **kwargs)
        return cache_page_for_anonymous(60 * 5)(super().dispatch)(
            request, *args, **kwargs
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["categories"] = Category.objects.all()
        context["last_posts"] = Blog.objects.filter(
            is_published=True, is_approved=True
        ).order_by("-created_at")[:3]
        return context


class BlogListView(ListView):
    """Показывает список публикаций с фильтрацией и поиском."""

    model = Blog
    template_name = "blog/page_list.html"
    context_object_name = "public_posts"
    paginate_by = 12

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return super().dispatch(request, *args, **kwargs)
        return cache_page_for_anonymous(60 * 5)(super().dispatch)(
            request, *args, **kwargs
        )

    def get_queryset(self):
        query = self.request.GET.get("q", "").strip()
        category_id = self.request.GET.get("category")

        if self.request.user.is_authenticated and (
            self.request.user.has_perm("blog.can_approve_blog")
            or self.request.user.is_superuser
        ):
            posts = Blog.objects.all()
        elif self.request.user.is_authenticated:
            posts = Blog.objects.filter(
                Q(is_published=True, is_approved=True) | Q(author=self.request.user)
            )
        else:
            posts = Blog.objects.filter(is_published=True, is_approved=True)

        if category_id:
            posts = posts.filter(category_id=category_id)

        if query:
            posts = posts.filter(
                Q(title__icontains=query) | Q(content__icontains=query)
            )

        return posts.order_by("-created_at")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["categories"] = Category.objects.all()
        selected_category_id = self.request.GET.get("category", "")
        context["selected_category"] = selected_category_id
        context["current_category"] = None
        if selected_category_id:
            context["current_category"] = Category.objects.filter(
                pk=selected_category_id
            ).first()
        query = self.request.GET.get("q", "").strip()

        if self.request.user.is_authenticated:
            my_posts = Blog.objects.filter(author=self.request.user)
            if category_id := self.request.GET.get("category"):
                my_posts = my_posts.filter(category_id=category_id)
            if query:
                my_posts = my_posts.filter(
                    Q(title__icontains=query) | Q(content__icontains=query)
                )
            context["my_posts"] = my_posts.order_by("-created_at")
        else:
            context["my_posts"] = Blog.objects.none()

        context["query"] = query
        return context


class BlogDetailView(DetailView):
    """Показывает отдельную статью и увеличивает счётчик просмотров."""

    model = Blog
    template_name = "blog/page_detail.html"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return super().dispatch(request, *args, **kwargs)
        return cache_page_for_anonymous(60 * 5)(super().dispatch)(
            request, *args, **kwargs
        )

    def get_queryset(self):
        if self.request.user.is_authenticated:
            if (
                self.request.user.has_perm("blog.can_approve_blog")
                or self.request.user.is_superuser
            ):
                return Blog.objects.all()
            return Blog.objects.filter(
                Q(is_published=True, is_approved=True) | Q(author=self.request.user)
            )
        return Blog.objects.filter(is_published=True, is_approved=True)

    def get_object(self, queryset=None):
        self.object = super().get_object(queryset)
        Blog.objects.filter(pk=self.object.pk).update(views_count=F("views_count") + 1)
        self.object.refresh_from_db(fields=["views_count"])
        return self.object

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        obj = self.object
        base_qs = Blog.objects.filter(is_published=True)
        if self.request.user.is_authenticated and self.request.user == obj.author:
            base_qs = Blog.objects.filter(
                Q(is_published=True) | Q(author=self.request.user)
            )

        context["next_post"] = (
            base_qs.filter(created_at__lt=obj.created_at)
            .order_by("-created_at")
            .first()
        )
        context["previous_post"] = (
            base_qs.filter(created_at__gt=obj.created_at).order_by("created_at").first()
        )
        return context


class BlogCreateView(LoginRequiredMixin, AuthorRoleRequiredMixin, CreateView):
    """Создаёт статью для обычного автора или администратора."""

    model = Blog
    form_class = BlogForm
    template_name = "blog/page_form.html"
    success_url = reverse_lazy("blog:blog_list")

    def form_valid(self, form):
        form.instance.author = self.request.user
        action = self.request.POST.get("action")

        if action == "draft":
            form.instance.is_published = False
            form.instance.is_approved = False
        elif action == "submit" and not (
            self.request.user.has_perm("blog.can_approve_blog")
            or self.request.user.is_superuser
        ):
            form.instance.is_published = True
            form.instance.is_approved = False
        elif (
            self.request.user.has_perm("blog.can_approve_blog")
            or self.request.user.is_superuser
        ):
            if form.instance.is_published and not form.instance.is_approved:
                form.instance.is_approved = True
        else:
            form.instance.is_published = False
            form.instance.is_approved = False

        return super().form_valid(form)


class BlogUpdateView(LoginRequiredMixin, UpdateView):
    """Редактирует статью с учётом роли пользователя и статуса публикации."""

    model = Blog
    form_class = BlogForm
    template_name = "blog/page_form.html"

    def get_queryset(self):
        if self.request.user.is_superuser or self.request.user.has_perm(
            "blog.can_approve_blog"
        ):
            return Blog.objects.all()
        return Blog.objects.filter(author=self.request.user)

    def get_success_url(self):
        return reverse("blog:blog_detail", args=[self.object.pk])

    def form_valid(self, form):
        form.instance.author = self.request.user
        action = self.request.POST.get("action")

        if action == "draft":
            form.instance.is_published = False
            form.instance.is_approved = False
        elif action == "submit" and not (
            self.request.user.is_superuser
            or self.request.user.has_perm("blog.can_approve_blog")
        ):
            form.instance.is_published = True
            form.instance.is_approved = False
        elif self.request.user.is_superuser or self.request.user.has_perm(
            "blog.can_approve_blog"
        ):
            if form.instance.is_published:
                form.instance.is_approved = False
        else:
            form.instance.is_published = False
            form.instance.is_approved = False

        return super().form_valid(form)


class CategoryListView(ListView):
    """Выводит список всех категорий дневника."""

    model = Category
    template_name = "blog/category.html"
    context_object_name = "categories"

    def get_queryset(self):
        return Category.objects.all()


class BlogDeleteView(LoginRequiredMixin, DeleteView):
    """Удаляет статью автора."""

    model = Blog
    template_name = "blog/page_confirm_delete.html"

    def get_queryset(self):
        return Blog.objects.filter(author=self.request.user)

    success_url = reverse_lazy("blog:blog_list")


class BlogSubmitForReviewView(LoginRequiredMixin, View):
    """Переводит черновик автора в статус ожидания модерации."""

    def post(self, request, pk):
        blog = get_object_or_404(Blog, pk=pk, author=request.user)
        if blog.is_published:
            return redirect("blog:blog_detail", pk=pk)

        blog.is_published = True
        blog.is_approved = False
        blog.save(update_fields=["is_published", "is_approved"])
        return redirect("blog:blog_detail", pk=pk)


def send_moderation_email(blog, approved):
    """Отправляет автору письмо о результате модерации."""

    title = blog.title
    if approved:
        subject = f'Ваша статья "{title}" одобрена'
        message = f'Ваша статья "{title}" одобрена на публикацию.'
    else:
        subject = f'Ваша статья "{title}" не одобрена'
        message = f'Ваша статья "{title}" не одобрена на публикацию.'

    send_mail(
        subject=subject,
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[blog.author.email],
        fail_silently=False,
    )


def redirect_to_referer_or_detail(request, pk):
    """Возвращает пользователя на предыдущую страницу или в детальную статью."""

    referer = request.META.get("HTTP_REFERER")
    if referer:
        return redirect(referer)
    return redirect("blog:blog_detail", pk=pk)


class BlogTogglePublishView(LoginRequiredMixin, UserPassesTestMixin, View):
    """Публикует, подтверждает или снимает статью с публикации."""

    def test_func(self):
        return (
            self.request.user.has_perm("blog.can_approve_blog")
            or self.request.user.is_superuser
        )

    def post(self, request, pk):
        blog = get_object_or_404(Blog, pk=pk)
        if (
            not self.request.user.has_perm("blog.can_approve_blog")
            and not self.request.user.is_superuser
        ):
            return HttpResponse(status=403)

        if blog.is_published and not blog.is_approved:
            blog.is_approved = True
            blog.save(update_fields=["is_approved"])
            send_moderation_email(blog, approved=True)
        elif not blog.is_published:
            blog.is_published = True
            blog.is_approved = True
            blog.save(update_fields=["is_published", "is_approved"])
            send_moderation_email(blog, approved=True)
        else:
            blog.is_published = False
            blog.is_approved = False
            blog.save(update_fields=["is_published", "is_approved"])
            send_moderation_email(blog, approved=False)

        return redirect_to_referer_or_detail(request, pk)


class BlogRejectView(LoginRequiredMixin, UserPassesTestMixin, View):
    """Отклоняет статью на модерации."""

    def test_func(self):
        return (
            self.request.user.has_perm("blog.can_approve_blog")
            or self.request.user.is_superuser
        )

    def post(self, request, pk):
        blog = get_object_or_404(Blog, pk=pk)
        blog.is_published = False
        blog.is_approved = False
        blog.save(update_fields=["is_published", "is_approved"])

        send_moderation_email(blog, approved=False)
        return redirect_to_referer_or_detail(request, pk)


class ContactMessageView(TemplateView):
    """Показывает страницу успешной отправки сообщения."""

    template_name = "blog/contact_message.html"


class ContactsView(View):
    """Обрабатывает форму обратной связи."""

    template_name = "blog/contacts.html"

    def get(self, request):
        form = ContactForm()
        return render(request, self.template_name, {"form": form})

    def post(self, request):
        form = ContactForm(request.POST)
        if not form.is_valid():
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
            return render(request, self.template_name, {"form": form})

        name = form.cleaned_data["name"]
        email = form.cleaned_data["email"]
        message_text = form.cleaned_data["message"]

        admin_email = (
            os.getenv("ADMIN_EMAIL")
            or settings.DEFAULT_FROM_EMAIL
            or settings.SERVER_EMAIL
        )

        send_mail(
            subject=f"Новое сообщение от {name}",
            message=f"Имя: {name}\nEmail: {email}\n\n{message_text}",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[admin_email],
            fail_silently=False,
        )

        messages.success(request, "Сообщение отправлено. Спасибо!")
        return redirect("blog:contact_message")


def tinymce_image_upload(request):
    """Сохраняет изображение TinyMCE и создаёт адаптивные WEBP-варианты."""

    if request.method == "POST" and request.FILES.get("file"):
        file = request.FILES["file"]
        filename = os.path.basename(file.name)
        storage_path = os.path.join("blog", "originals", filename)

        raw_content = file.read()
        saved_path = default_storage.save(
            storage_path, ContentFile(raw_content, name=filename)
        )
        base_name = os.path.splitext(os.path.basename(saved_path))[0]

        variants = build_responsive_webp_variants(BytesIO(raw_content), base_name)
        default_storage.save(
            os.path.join("blog", "desktop", variants["desktop"].name),
            variants["desktop"],
        )
        default_storage.save(
            os.path.join("blog", "tablets", variants["tablet"].name), variants["tablet"]
        )
        default_storage.save(
            os.path.join("blog", "mobile", variants["mobile"].name), variants["mobile"]
        )

        file_url = default_storage.url(saved_path)

        return JsonResponse({"location": file_url})

    return JsonResponse({"error": "Invalid request"}, status=400)
