from pathlib import Path

from django.core.management import call_command
from django.core.management.base import BaseCommand

from inventory.models import Product


class Command(BaseCommand):
    help = 'Load inventory seed data when the product table is empty.'

    def handle(self, *args, **options):
        existing_count = Product.objects.count()
        if existing_count:
            self.stdout.write(self.style.SUCCESS(f'Skipping inventory seed; {existing_count} products already exist.'))
            return

        fixture_path = Path(__file__).resolve().parents[3] / 'fixtures' / 'inventory_seed.json'
        if not fixture_path.exists():
            self.stdout.write(self.style.ERROR(f'Inventory seed fixture not found: {fixture_path}'))
            raise SystemExit(1)

        call_command('loaddata', str(fixture_path))
        seeded_count = Product.objects.count()
        self.stdout.write(self.style.SUCCESS(f'Inventory seed complete; {seeded_count} products loaded.'))
