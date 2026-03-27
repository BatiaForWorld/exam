"""Служебные views проекта для обработки системных страниц."""

from django.shortcuts import render


def custom_page_not_found(request, exception):
    """Отображает пользовательскую страницу ошибки 404."""

    return render(request, "404.html", status=404)
