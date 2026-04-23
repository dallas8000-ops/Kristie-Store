from pathlib import Path
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.core.management.base import BaseCommand

from inventory.models import Category, Product

DEFAULT_SIZE_RANGE = 'XS,S,M,L,XL,XXL'
SUPPORTED_IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.webp'}


def _display_name_from_stem(stem):
    text = stem.replace('_', ' ').replace('-', ' ').strip()
    if not text:
        return 'Catalog Item'
    return ' '.join(part.capitalize() for part in text.split())


def _price_from_name(name):
    seed = sum(ord(ch) for ch in name.lower() if ch.isalnum())
    base = Decimal('34.00') + Decimal(seed % 137)
    cents = Decimal(seed % 4) * Decimal('0.25')
    return (base + cents).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def _old_price_from_price(price):
    return (price * Decimal('1.22')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

class Command(BaseCommand):
    help = 'Load inventory products from files in the workspace images folder.'

    def handle(self, *args, **options):
        cat, _ = Category.objects.get_or_create(name='Default', defaults={'description': 'Default category'})

        workspace_images = Path(settings.BASE_DIR).parent / 'images'
        if not workspace_images.exists():
            self.stdout.write(self.style.WARNING('No images folder found at workspace root.'))
            return

        image_files = [
            file_path for file_path in workspace_images.iterdir()
            if file_path.is_file() and file_path.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS
        ]
        if not image_files:
            self.stdout.write(self.style.WARNING('No image files found in workspace images folder.'))
            return

        created_count = 0
        updated_count = 0
        for image_file in sorted(image_files, key=lambda p: p.name.lower()):
            product_name = _display_name_from_stem(image_file.stem)
            price = _price_from_name(product_name)
            old_price = _old_price_from_price(price)

            _, created = Product.objects.update_or_create(
                name=product_name,
                defaults={
                    'description': '',
                    'price': price,
                    'old_price': old_price,
                    'category': cat,
                    'color': '',
                    'sizes': DEFAULT_SIZE_RANGE,
                }
            )
            if created:
                created_count += 1
            else:
                updated_count += 1

        self.stdout.write(self.style.SUCCESS(
            f'Inventory loaded from images. Created {created_count} new products, updated {updated_count} existing products.'
        ))
