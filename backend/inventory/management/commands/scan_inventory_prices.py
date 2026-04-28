from django.core.management.base import BaseCommand
from django.conf import settings

from inventory.models import Product
from inventory.pricing import apply_price_suggestion, suggest_price_for_product


class Command(BaseCommand):
    help = 'Scan inventory and suggest/apply prices from web and local comparables.'

    def _print_source_mode(self, allow_local_reference: bool) -> None:
        has_web_key = bool(getattr(settings, 'SERPAPI_API_KEY', '').strip())
        if has_web_key:
            self.stdout.write('Price source mode: SerpAPI + fallback web lookup + local reference.')
            return
        if allow_local_reference:
            self.stdout.write('Price source mode: fallback web lookup + local reference (local-only allowed).')
            return
        self.stdout.write(
            'Price source mode: fallback web lookup + local reference (local-only updates are blocked).'
        )

    @staticmethod
    def _build_queryset(options):
        qs = Product.objects.select_related('category').all().order_by('id')

        if options['only_missing']:
            qs = qs.filter(price_usd__lte=0)

        if options['limit'] and options['limit'] > 0:
            qs = qs[:options['limit']]

        return qs

    @staticmethod
    def _can_apply(suggestion, allow_local_reference: bool, min_confidence: float) -> bool:
        if suggestion.source == 'local-reference' and not allow_local_reference:
            return False
        if suggestion.confidence < min_confidence:
            return False
        return True

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Only print suggested prices.')
        parser.add_argument('--only-missing', action='store_true', help='Scan products with missing/zero USD price only.')
        parser.add_argument('--limit', type=int, default=0, help='Limit number of products processed.')
        parser.add_argument('--min-confidence', type=float, default=0.45, help='Minimum confidence to apply update.')
        parser.add_argument(
            '--allow-local-reference',
            action='store_true',
            help='Allow updates using local-reference source when web comparison is unavailable.',
        )

    def handle(self, *args, **options):
        allow_local_reference = options['allow_local_reference']
        self._print_source_mode(allow_local_reference)
        qs = self._build_queryset(options)

        total = 0
        updated = 0
        skipped = 0

        for product in qs:
            total += 1
            suggestion = suggest_price_for_product(product)

            if suggestion.price_usd is None:
                skipped += 1
                self.stdout.write(self.style.WARNING(
                    f"[{product.id}] {product.name}: no suggestion ({suggestion.reason})"
                ))
                continue

            self.stdout.write(
                f"[{product.id}] {product.name}: USD {suggestion.price_usd} | UGX {suggestion.price_ugx} "
                f"| confidence={suggestion.confidence} | samples={suggestion.sample_size} | source={suggestion.source}"
            )

            if options['dry_run']:
                continue

            if not self._can_apply(suggestion, allow_local_reference, options['min_confidence']):
                skipped += 1
                continue

            if apply_price_suggestion(product, suggestion):
                updated += 1

        msg = f'Processed {total} products. Updated {updated}, skipped {skipped}.'
        if options['dry_run']:
            self.stdout.write(self.style.SUCCESS(f'Dry run complete. {msg}'))
        else:
            self.stdout.write(self.style.SUCCESS(msg))
