import os

from django.core.management import BaseCommand, CommandError

from users.models import User


class Command(BaseCommand):
    def handle(self, *args, **kwargs):
        email = os.getenv("ADMIN_EMAIL")
        password = os.getenv("ADMIN_PASSWORD")

        if not email or not password:
            raise CommandError("ADMIN_EMAIL и ADMIN_PASSWORD должны быть заданы")

        user, created = User.objects.get_or_create(email=email)
        user.set_password(password)
        user.is_active = True
        user.is_staff = True
        user.is_superuser = True
        user.save()

        message = "Администратор создан!!!" if created else "Администратор обновлён!!!"
        self.stdout.write(self.style.SUCCESS(message))
