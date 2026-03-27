from django.core.management.base import BaseCommand
from django.core.management import call_command


class Command(BaseCommand):
    help = "Очистка базы данных — удаляет все данные через flush"

    def handle(self, *args, **kwargs):
        # Flush удаляет все данные из всех таблиц, но сохраняет структуру миграций.
        call_command("flush", verbosity=1, interactive=False)
        self.stdout.write(self.style.SUCCESS("База данных полностью очищенна."))
