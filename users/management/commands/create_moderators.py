from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from blog.models import Blog


class Command(BaseCommand):
    help = "Создание группы модераторов статей"

    def handle(self, *args, **options):
        content_type = ContentType.objects.get_for_model(Blog)

        permissions = Permission.objects.filter(
            content_type=content_type,
            codename__in=[
                "add_blog",
                "change_blog",
                "delete_blog",
                "can_approve_blog",
            ],
        )

        group, created = Group.objects.get_or_create(name="Модераторы")

        group.permissions.set(permissions)
        group.save()

        if created:
            self.stdout.write(self.style.SUCCESS('Группа "Модератор статей" создана'))
        else:
            self.stdout.write(
                self.style.WARNING(
                    'Группа "Модератор статей" уже существует, права обновлены'
                )
            )
