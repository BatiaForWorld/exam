from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Загрузить тестовые данные из фикстур"

    def handle(self, *args, **kwargs):
        call_command("loaddata", "fixtures/users_fixtures.json")
        self.stdout.write(
            self.style.SUCCESS("Данные из фикстуры пользователей успешно загружены")
        )
