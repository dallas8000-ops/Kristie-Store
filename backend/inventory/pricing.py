from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from statistics import median
from typing import Iterable
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen

from django.conf import settings

from .models import Product

logger = logging.getLogger(__name__)

MONEY_QUANT = Decimal('0.01')
DEFAULT_UGX_RATE = Decimal('3700')
DDG_MIN_PRICE = Decimal('8')
DDG_MAX_PRICE = Decimal('1200')


@dataclass
class PriceSuggestion:
    price_usd: Decimal | None
    price_ugx: Decimal | None
    confidence: float
    sample_size: int
    source: str
    query: str
    links: list[str]
    reason: str = ''


def _to_decimal(value) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    cleaned = re.sub(r'[^0-9.]', '', str(value))
    if not cleaned:
        return None
    try:
        return Decimal(cleaned)
    except Exception:
        return None


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


def _iqr_filter(values: Iterable[Decimal]) -> list[Decimal]:
    ordered = sorted(values)
    if len(ordered) < 4:
        return ordered

    midpoint = len(ordered) // 2
    lower = ordered[:midpoint]
    upper = ordered[midpoint + (0 if len(ordered) % 2 == 0 else 1):]
    if not lower or not upper:
        return ordered

    q1 = Decimal(str(median(lower)))
    q3 = Decimal(str(median(upper)))
    iqr = q3 - q1
    if iqr <= 0:
        return ordered

    min_allowed = q1 - (Decimal('1.5') * iqr)
    max_allowed = q3 + (Decimal('1.5') * iqr)
    filtered = [v for v in ordered if min_allowed <= v <= max_allowed]
    return filtered or ordered


def _shopping_query(product: Product) -> str:
    category_name = (product.category.name if product.category_id else '').strip()
    base = f"{product.name} {category_name} women's clothing"
    return re.sub(r'\s+', ' ', base).strip()


def _fetch_serpapi_prices(query: str, api_key: str) -> tuple[list[Decimal], list[str]]:
    params = {
        'engine': 'google_shopping',
        'q': query,
        'api_key': api_key,
        'gl': 'us',
        'hl': 'en',
        'num': '20',
    }
    url = f"https://serpapi.com/search.json?{urlencode(params)}"

    with urlopen(url, timeout=20) as response:
        payload = json.loads(response.read().decode('utf-8'))

    prices: list[Decimal] = []
    links: list[str] = []

    for item in payload.get('shopping_results', []):
        price = _to_decimal(item.get('extracted_price') or item.get('price'))
        if price is None or price <= 0:
            continue
        prices.append(_money(price))
        link = item.get('link')
        if link:
            links.append(link)

    return prices, links


def _fetch_duckduckgo_prices(query: str) -> tuple[list[Decimal], list[str]]:
    params = {
        'q': f'{query} price USD',
        'ia': 'web',
    }
    url = f"https://duckduckgo.com/html/?{urlencode(params)}"

    request = Request(
        url,
        headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36',
            'Accept-Language': 'en-US,en;q=0.9',
        },
    )

    with urlopen(request, timeout=20) as response:
        html = response.read().decode('utf-8', errors='ignore')

    prices: list[Decimal] = []
    links: list[str] = []

    # Pull plausible USD-looking amounts from snippets/anchors.
    for match in re.findall(r'\$\s*(\d{1,4}(?:\.\d{1,2})?)', html):
        value = _to_decimal(match)
        if value is None:
            continue
        if not (DDG_MIN_PRICE <= value <= DDG_MAX_PRICE):
            continue
        prices.append(_money(value))

    for match in re.findall(r'href="(https?://[^"]+)"', html):
        if 'duckduckgo.com' in match:
            continue
        links.append(match)

    return prices[:24], links[:8]


def _fetch_web_prices_for_product(product: Product, query: str, api_key: str) -> tuple[list[Decimal], list[str], str]:
    prices: list[Decimal] = []
    links: list[str] = []
    source = 'local-reference'

    if api_key:
        try:
            lens_prices: list[Decimal] = []
            image_url = _product_image_url(product)
            if image_url:
                lens_prices, lens_links = _fetch_serpapi_lens_prices(image_url, api_key)
                prices.extend(lens_prices)
                links.extend(lens_links[:3])

            web_prices, web_links = _fetch_serpapi_prices(query, api_key)
            prices.extend(web_prices)
            links.extend(web_links[:5])
            if lens_prices or web_prices:
                source = 'serpapi+local-reference'
            return prices, links, source
        except Exception as exc:
            logger.warning('Price scan web lookup failed for %s: %s', product.pk, exc)

    try:
        ddg_prices, ddg_links = _fetch_duckduckgo_prices(query)
        prices.extend(ddg_prices)
        links.extend(ddg_links[:5])
        if ddg_prices:
            source = 'ddg-web+local-reference'
    except Exception as exc:
        logger.warning('DDG web price lookup failed for %s: %s', product.pk, exc)

    return prices, links, source


def _product_image_url(product: Product) -> str:
    first_image = product.images.first()
    if not first_image:
        return ''

    image_value = str(first_image.image)
    if not image_value:
        return ''

    if image_value.startswith('http://') or image_value.startswith('https://'):
        return image_value

    base_url = getattr(settings, 'PRICE_SCAN_SITE_BASE_URL', '').strip()
    if not base_url:
        return ''

    return urljoin(base_url.rstrip('/') + '/', f"media/{image_value.lstrip('/')}")


def _fetch_serpapi_lens_prices(image_url: str, api_key: str) -> tuple[list[Decimal], list[str]]:
    params = {
        'engine': 'google_lens',
        'url': image_url,
        'api_key': api_key,
        'hl': 'en',
    }
    url = f"https://serpapi.com/search.json?{urlencode(params)}"

    with urlopen(url, timeout=20) as response:
        payload = json.loads(response.read().decode('utf-8'))

    prices: list[Decimal] = []
    links: list[str] = []

    for item in payload.get('visual_matches', []):
        raw_price = item.get('price')
        if isinstance(raw_price, dict):
            raw_price = raw_price.get('extracted_value') or raw_price.get('value')
        price = _to_decimal(raw_price)
        if price is None or price <= 0:
            continue
        prices.append(_money(price))
        link = item.get('link')
        if link:
            links.append(link)

    return prices, links


def _local_reference_prices(product: Product) -> list[Decimal]:
    qs = Product.objects.filter(in_stock=True, price_usd__gt=0).exclude(pk=product.pk)
    if product.category_id:
        qs = qs.filter(category_id=product.category_id)

    values = [p.price_usd for p in qs[:60] if p.price_usd and p.price_usd > 0]
    return [_money(v) for v in values]


def suggest_price_for_product(product: Product) -> PriceSuggestion:
    ugx_rate = _to_decimal(getattr(settings, 'PRICE_SCAN_UGX_RATE', DEFAULT_UGX_RATE)) or DEFAULT_UGX_RATE
    query = _shopping_query(product)

    all_prices: list[Decimal] = []
    links: list[str] = []

    api_key = getattr(settings, 'SERPAPI_API_KEY', '').strip()
    web_prices, web_links, web_source = _fetch_web_prices_for_product(product, query, api_key)
    all_prices.extend(web_prices)
    links.extend(web_links)
    source = web_source

    local_prices = _local_reference_prices(product)
    all_prices.extend(local_prices)

    all_prices = [p for p in all_prices if p > 0]
    if not all_prices:
        return PriceSuggestion(
            price_usd=None,
            price_ugx=None,
            confidence=0.0,
            sample_size=0,
            source='none',
            query=query,
            links=[],
            reason='No comparable prices found.',
        )

    filtered = _iqr_filter(all_prices)
    suggested_usd = _money(Decimal(str(median(filtered))))
    suggested_ugx = _money(suggested_usd * ugx_rate)

    sample_size = len(filtered)
    confidence = min(0.95, 0.3 + (min(sample_size, 12) * 0.045))
    if source == 'local-reference':
        confidence *= 0.8
    confidence = round(confidence, 2)

    return PriceSuggestion(
        price_usd=suggested_usd,
        price_ugx=suggested_ugx,
        confidence=confidence,
        sample_size=sample_size,
        source=source,
        query=query,
        links=links[:5],
    )


def apply_price_suggestion(product: Product, suggestion: PriceSuggestion) -> bool:
    if suggestion.price_usd is None or suggestion.price_ugx is None:
        return False

    update_fields = ['price_usd', 'price_ugx', 'updated_at']
    current_price = product.price_usd

    if current_price and current_price > 0 and current_price != suggestion.price_usd:
        product.old_price = current_price
        update_fields.append('old_price')

    product.price_usd = suggestion.price_usd
    product.price_ugx = suggestion.price_ugx
    product.save(update_fields=update_fields)
    return True
