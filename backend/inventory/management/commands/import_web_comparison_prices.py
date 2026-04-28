from __future__ import annotations

import csv
from collections import defaultdict
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from inventory.models import Product


def _to_decimal(value: str) -> Decimal | None:
    cleaned = (value or '').strip().replace('$', '').replace(',', '')
    if not cleaned:
        return None
    try:
        amount = Decimal(cleaned)
    except InvalidOperation:
        return None
    if amount <= 0:
        return None
    return amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def _median_decimal(values: list[Decimal]) -> Decimal:
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2 == 1:
        return ordered[mid]
    return ((ordered[mid - 1] + ordered[mid]) / Decimal('2')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


class Command(BaseCommand):
    help = 'Import web comparison prices from CSV and apply median USD/UGX price per product.'

    @staticmethod
    def _resolve_csv_path(path_value: str) -> Path:
        csv_path = Path(path_value)
        if csv_path.is_absolute():
            return csv_path
        return Path.cwd() / csv_path

    @staticmethod
    def _parse_csv(csv_path: Path) -> tuple[dict[int, list[Decimal]], dict[str, list[Decimal]], int]:
        by_product_id: dict[int, list[Decimal]] = defaultdict(list)
        by_product_name: dict[str, list[Decimal]] = defaultdict(list)
        bad_rows = 0

        with csv_path.open('r', encoding='utf-8-sig', newline='') as fp:
            reader = csv.DictReader(fp)
            required = {'product_name', 'price_usd'}
            if not required.issubset(set(reader.fieldnames or [])):
                raise CommandError('CSV must include headers: product_name, price_usd (optional: product_id, source_url)')

            for row in reader:
                price = _to_decimal(row.get('price_usd', ''))
                if price is None:
                    bad_rows += 1
                    continue

                product_id_raw = (row.get('product_id') or '').strip()
                if product_id_raw.isdigit():
                    by_product_id[int(product_id_raw)].append(price)
                    continue

                product_name = (row.get('product_name') or '').strip().lower()
                if not product_name:
                    bad_rows += 1
                    continue
                by_product_name[product_name].append(price)

        return by_product_id, by_product_name, bad_rows

    @staticmethod
    def _prices_for_product(product: Product, by_product_id: dict[int, list[Decimal]], by_product_name: dict[str, list[Decimal]]) -> list[Decimal]:
        prices = by_product_id.get(product.id)
        if prices:
            return prices
        return by_product_name.get(product.name.strip().lower(), [])

    @staticmethod
    def _apply_price(product: Product, usd_price: Decimal, ugx_price: Decimal) -> None:
        if product.price_usd and product.price_usd > 0 and product.price_usd != usd_price:
            product.old_price = product.price_usd

        product.price_usd = usd_price
        product.price_ugx = ugx_price
        product.save(update_fields=['price_usd', 'price_ugx', 'old_price', 'updated_at'])

    @staticmethod
    def _count_unmatched_groups(by_product_name: dict[str, list[Decimal]], products) -> int:
        matched_names = {p.name.strip().lower() for p in products}
        return sum(1 for name in by_product_name if name not in matched_names)

    def add_arguments(self, parser):
        parser.add_argument(
            '--csv',
            default='fixtures/web_price_comparisons.csv',
            help='CSV path relative to backend/ (default: fixtures/web_price_comparisons.csv)',
        )
        parser.add_argument('--dry-run', action='store_true', help='Preview updates without saving.')
        parser.add_argument('--min-samples', type=int, default=1, help='Minimum price samples per product (default: 1).')
        parser.add_argument('--ugx-rate', type=Decimal, default=Decimal('3700'), help='USD to UGX conversion rate (default: 3700).')

    def handle(self, *args, **options):
        if options['min_samples'] < 1:
            raise CommandError('--min-samples must be at least 1.')

        csv_path = self._resolve_csv_path(options['csv'])

        if not csv_path.exists():
            raise CommandError(f'CSV not found: {csv_path}')

        by_product_id, by_product_name, bad_rows = self._parse_csv(csv_path)

        products = Product.objects.all()
        updated = 0
        skipped = 0

        for product in products:
            prices = self._prices_for_product(product, by_product_id, by_product_name)

            if not prices:
                continue

            if len(prices) < options['min_samples']:
                skipped += 1
                continue

            usd_price = _median_decimal(prices)
            ugx_price = (usd_price * options['ugx_rate']).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

            self.stdout.write(
                f'[{product.id}] {product.name}: samples={len(prices)} -> USD {usd_price} | UGX {ugx_price}'
            )

            if options['dry_run']:
                continue

            self._apply_price(product, usd_price, ugx_price)
            updated += 1

        unmatched_groups = self._count_unmatched_groups(by_product_name, products)

        self.stdout.write(self.style.SUCCESS(
            f'Processed CSV groups. Updated {updated} product(s), skipped {skipped} (min-samples), '
            f'unmatched groups {unmatched_groups}, bad rows {bad_rows}.'
        ))