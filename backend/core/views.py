from pathlib import Path
from datetime import timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import json
import requests as _requests

from django.conf import settings
from django.contrib.auth import login, logout
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib import messages
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Prefetch
from django.http import FileResponse, Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from cart.models import Cart, CartItem, Order, OrderItem
from inventory.models import Product, ProductImage
from pages.forms import ContactInquiryForm
from pages.models import ContactInquiry


SUPPORTED_IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.webp'}
SUPPORTED_CURRENCIES = ('USD', 'EUR', 'KES', 'UGX')
PAYMENT_METHODS = ('mtn', 'airtel', 'worldremit')
FALLBACK_RATES = {
    'USD': Decimal('1'),
    'EUR': Decimal('0.92'),
    'KES': Decimal('129.50'),
    'UGX': Decimal('3820'),
}


STALE_EMPTY_CART_DAYS = 7


def _workspace_images_dir():
    return Path(settings.BASE_DIR).parent / 'images'


def _ensure_session_key(request):
    if not request.session.session_key:
        request.session.create()
    return request.session.session_key


def _cleanup_stale_empty_guest_carts(active_session_key=None):
    cutoff = timezone.now() - timedelta(days=STALE_EMPTY_CART_DAYS)
    stale_carts = Cart.objects.filter(
        user__isnull=True,
        created_at__lt=cutoff,
        items__isnull=True,
    )

    if active_session_key:
        stale_carts = stale_carts.exclude(session_key=active_session_key)

    stale_carts.delete()


def _current_cart(request, create=False):
    active_session_key = request.session.session_key
    _cleanup_stale_empty_guest_carts(active_session_key=active_session_key)

    if request.user.is_authenticated:
        if create:
            cart, _ = Cart.objects.get_or_create(
                user=request.user,
                defaults={'session_key': request.session.session_key}
            )
            return cart
        return Cart.objects.filter(user=request.user).first()

    session_key = _ensure_session_key(request)
    if create:
        cart, _ = Cart.objects.get_or_create(session_key=session_key, user=None)
        return cart
    return Cart.objects.filter(session_key=session_key, user=None).first()


def _merge_guest_cart_into_user(request, user, session_key=None):
    session_key = session_key or request.session.session_key
    if not session_key:
        return

    guest_cart = Cart.objects.filter(session_key=session_key, user=None).first()
    if not guest_cart:
        return

    user_cart, _ = Cart.objects.get_or_create(user=user, defaults={'session_key': session_key})

    for guest_item in guest_cart.items.select_related('product'):
        user_item, created = CartItem.objects.get_or_create(
            cart=user_cart,
            product=guest_item.product,
            size=guest_item.size,
            color=guest_item.color,
            defaults={'quantity': guest_item.quantity},
        )
        if not created:
            user_item.quantity += guest_item.quantity
            user_item.save()

    guest_cart.delete()


def _catalog_image_files():
    image_dir = _workspace_images_dir()
    if not image_dir.exists():
        return []

    files = [
        f for f in image_dir.iterdir()
        if f.is_file() and f.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS
    ]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files


def _product_image_url(image_field):
    image_name = Path(str(image_field)).name
    return reverse('catalog_image', args=[image_name])


def _normalize_key(value):
    return ''.join(char for char in value.lower() if char.isalnum())


def _display_name_from_stem(stem):
    text = stem.replace('_', ' ').replace('-', ' ').strip()
    if not text:
        return 'Catalog Item'
    return ' '.join(part.capitalize() for part in text.split())


def _catalog_fallback_description(product):
    name = (product.name or '').lower()

    color_keywords = {
        'black': 'black',
        'white': 'white',
        'ivory': 'ivory',
        'cream': 'cream',
        'navy': 'navy',
        'blue': 'blue',
        'teal': 'teal',
        'green': 'green',
        'emerald': 'emerald',
        'olive': 'olive',
        'purple': 'purple',
        'violet': 'violet',
        'lilac': 'lilac',
        'pink': 'pink',
        'blush': 'blush',
        'magenta': 'magenta',
        'fuchsia': 'fuchsia',
        'peach': 'peach',
        'yellow': 'yellow',
        'lemon': 'lemon',
        'mustard': 'mustard',
        'gold': 'gold',
        'orange': 'orange',
        'tan': 'tan',
        'camel': 'camel',
        'oatmeal': 'oatmeal',
        'grey': 'grey',
        'gray': 'gray',
        'burgundy': 'burgundy',
        'maroon': 'maroon',
        'red': 'red',
        'scarlet': 'scarlet',
        'rust': 'rust',
    }

    type_keywords = {
        'pantsuit': 'pantsuit',
        'suit': 'suit set',
        'blazer': 'blazer set',
        'waistcoat': 'waistcoat set',
        'dress': 'dress',
        'midi': 'midi dress',
        'mini': 'mini dress',
        'maxi': 'maxi dress',
        'gown': 'gown',
        'cocktail': 'cocktail look',
        'sheath': 'sheath silhouette',
        'wrap': 'wrap silhouette',
        'skirt': 'skirt set',
        'office': 'office-ready outfit',
    }

    vibe_phrases = [
        'made for polished daytime styling.',
        'ideal for elevated work-to-evening wear.',
        'crafted for confident, modern dressing.',
        'designed to stand out at special occasions.',
        'built for comfort with a refined finish.',
        'tailored for effortless, versatile outfits.',
    ]

    color = ''
    for keyword, label in color_keywords.items():
        if keyword in name:
            color = label
            break

    item_type = 'fashion piece'
    for keyword, label in type_keywords.items():
        if keyword in name:
            item_type = label
            break

    key = f'{product.name}:{product.id}'
    vibe = vibe_phrases[sum(ord(char) for char in key) % len(vibe_phrases)]

    if color:
        return f'A {color} {item_type} {vibe}'
    return f'A {item_type} {vibe}'


def _recent_images(limit=3):
    return _catalog_image_files()[:limit]


def _featured_products(limit=3):
    products = Product.objects.prefetch_related(
        Prefetch('images', queryset=ProductImage.objects.order_by('id'))
    ).filter(in_stock=True).order_by('-created_at')[:limit]

    featured = []
    for product in products:
        images = list(product.images.all())
        if not images:
            continue

        featured.append({
            'name': product.name,
            'description': (product.description or '').strip() or 'Curated premium fashion for confident everyday wear.',
            'price': _format_money(_safe_decimal(product.price, Decimal('0')), 'USD'),
            'image_url': _product_image_url(images[0].image),
            'sizes': product.size_list(),
        })
    return featured


def _safe_decimal(value, default):
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return default


def _format_money(amount, currency):
    decimals = Decimal('1') if currency == 'UGX' else Decimal('0.01')
    rounded = amount.quantize(decimals, rounding=ROUND_HALF_UP)
    return f'{rounded:,.0f}' if currency == 'UGX' else f'{rounded:,.2f}'


def _fetch_live_rates():
    url = 'https://api.frankfurter.app/latest?from=USD&to=EUR,KES,UGX'
    try:
        response = _requests.get(url, timeout=8)
        response.raise_for_status()
        payload = response.json()
        rates = {
            'USD': Decimal('1'),
            'EUR': _safe_decimal(payload.get('rates', {}).get('EUR'), FALLBACK_RATES['EUR']),
            'KES': _safe_decimal(payload.get('rates', {}).get('KES'), FALLBACK_RATES['KES']),
            'UGX': _safe_decimal(payload.get('rates', {}).get('UGX'), FALLBACK_RATES['UGX']),
        }
        return rates, payload.get('date', ''), 'live'
    except Exception as e:
        import sys
        print(f'Warning: Failed to fetch live exchange rates: {e}', file=sys.stderr)
        return FALLBACK_RATES, '', 'fallback'


def _checkout_preferences(request):
    currency = request.GET.get('currency') or request.session.get('currency') or 'USD'
    if currency not in SUPPORTED_CURRENCIES:
        currency = 'USD'
    request.session['currency'] = currency

    payment_method = request.GET.get('payment_method') or request.session.get('payment_method') or 'mtn'
    if payment_method not in PAYMENT_METHODS:
        payment_method = 'mtn'
    request.session['payment_method'] = payment_method

    rates, rates_updated, rates_source = _fetch_live_rates()
    rate = rates.get(currency, Decimal('1'))
    return {
        'currency': currency,
        'payment_method': payment_method,
        'rate': rate,
        'rates': rates,
        'rates_updated': rates_updated,
        'rates_source': rates_source,
    }


def _payment_instructions(country, payment_method):
    country_key = (country or '').strip().lower()
    business_name = 'Kristie Store'
    mtn_number = '+256XXXXXXXXX'
    airtel_number = '+256XXXXXXXXX'

    if country_key == 'uganda':
        if payment_method == 'airtel':
            number_line = f'Number: {airtel_number} (Airtel)'
        elif payment_method == 'worldremit':
            number_line = 'Use WorldRemit and send to the business mobile money details provided.'
        else:
            number_line = f'Number: {mtn_number} (MTN)'

        return (
            'UGANDA PAYMENT INSTRUCTIONS\n\n'
            f'Send payment to: {business_name}\n'
            f'{number_line}\n\n'
            'After payment, send your transaction screenshot/reference to confirm your order.'
        )

    return (
        'INTERNATIONAL PAYMENT INSTRUCTIONS\n\n'
        'Use WorldRemit (or equivalent) with the details below:\n'
        f'Receiver Name: {business_name}\n'
        'Country: Uganda\n'
        f'Receiver Number: {mtn_number}\n'
        'Network: MTN or Airtel\n\n'
        'After transfer, send payment confirmation so we can verify and dispatch.'
    )


def health(request):
    return render(request, 'core/health.html', status=200)


def home(request):
    if request.method == 'POST':
        contact_form = ContactInquiryForm(request.POST)
        if contact_form.is_valid():
            inquiry = ContactInquiry.objects.create(**contact_form.cleaned_data)
            send_mail(
                subject=f"New storefront inquiry: {inquiry.subject}",
                message=(
                    f"Name: {inquiry.name}\n"
                    f"Email: {inquiry.email}\n\n"
                    f"Message:\n{inquiry.message}"
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[settings.CONTACT_RECIPIENT_EMAIL],
                fail_silently=True,
            )
            messages.success(request, 'Message sent. We received your inquiry and will follow up soon.')
            return redirect('home')
        messages.error(request, 'Please correct the highlighted fields and try again.')
    else:
        contact_form = ContactInquiryForm()

    hero_images = _recent_images(limit=3)
    featured_products = _featured_products(limit=3)
    category_count = Product.objects.values('category').distinct().count()
    product_count = Product.objects.count()

    return render(request, 'core/index.html', {
        'hero_images': hero_images,
        'featured_products': featured_products,
        'contact_form': contact_form,
        'product_count': product_count,
        'category_count': category_count,
    })


def about(request):
    brand_images = _recent_images(limit=2)
    return render(request, 'core/about.html', {'brand_images': brand_images})


def signup_view(request):
    if request.user.is_authenticated:
        return redirect('home')

    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            pre_login_session_key = request.session.session_key
            user = form.save()
            login(request, user)
            _merge_guest_cart_into_user(request, user, session_key=pre_login_session_key)
            messages.success(request, 'Account created successfully. Welcome to East Africa Fashion.')
            return redirect('home')
        messages.error(request, 'Please correct the signup form and try again.')
    else:
        form = UserCreationForm()

    return render(request, 'core/auth_signup.html', {'form': form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect('home')

    form = AuthenticationForm(request, data=request.POST or None)
    if request.method == 'POST':
        if form.is_valid():
            pre_login_session_key = request.session.session_key
            user = form.get_user()
            login(request, user)
            _merge_guest_cart_into_user(request, user, session_key=pre_login_session_key)
            messages.success(request, f'Welcome back, {user.username}.')
            return redirect('home')
        messages.error(request, 'Invalid username or password.')

    return render(request, 'core/auth_login.html', {'form': form})


def logout_view(request):
    if request.method == 'POST':
        logout(request)
        messages.info(request, 'You have been signed out.')
    return redirect('home')


def catalog(request):
    products = Product.objects.prefetch_related(
        Prefetch('images', queryset=ProductImage.objects.order_by('id'))
    ).all().order_by('-created_at')

    catalog_items = []
    for product in products:
        images = list(product.images.all())
        if not images:
            continue

        primary_image = images[0]
        detail_image = images[1] if len(images) > 1 else primary_image
        description = (product.description or '').strip()
        if description.lower() == 'auto-created from uploaded catalog image.':
            description = ''

        catalog_items.append({
            'name': product.name,
            'description': description or _catalog_fallback_description(product),
            'price': product.price,
            'primary_url': _product_image_url(primary_image.image),
            'detail_url': _product_image_url(detail_image.image),
        })

    return render(request, 'core/catalog.html', {
        'catalog_items': catalog_items,
        'total_items': len(catalog_items),
    })


def catalog_image(_request, image_name):
    requested_name = Path(image_name).name

    # Try workspace image folder first (used by legacy catalog seed flow).
    workspace_dir = _workspace_images_dir().resolve()
    workspace_candidate = (workspace_dir / requested_name).resolve()
    if workspace_dir in workspace_candidate.parents and workspace_candidate.exists() and workspace_candidate.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS:
        return FileResponse(open(workspace_candidate, 'rb'))

    # Fallback to media folder where ProductImage files are stored on most deployments.
    media_root = Path(settings.MEDIA_ROOT).resolve()
    media_candidate = (media_root / requested_name).resolve()
    if media_root in media_candidate.parents and media_candidate.exists() and media_candidate.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS:
        return FileResponse(open(media_candidate, 'rb'))

    # Some files are nested (for example: media/products/products/<name>).
    for candidate in media_root.rglob(requested_name):
        resolved = candidate.resolve()
        if media_root in resolved.parents and resolved.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS:
            return FileResponse(open(resolved, 'rb'))

    raise Http404('Image not found.')


def inventory(request):
    try:
        checkout = _checkout_preferences(request)
        products = Product.objects.prefetch_related(
            Prefetch('images', queryset=ProductImage.objects.all())
        ).all()

        inventory_items = []
        for product in products:
            base_price = _safe_decimal(product.price, Decimal('0'))
            converted_price = base_price * checkout['rate']
            product_images = list(product.images.all())
            image_url = _product_image_url(product_images[0].image) if product_images else ''
            inventory_items.append({
                'product': product,
                'price_display': _format_money(converted_price, checkout['currency']),
                'image_url': image_url,
            })

        return render(request, 'core/inventory.html', {
            'inventory_items': inventory_items,
            'currency': checkout['currency'],
            'supported_currencies': SUPPORTED_CURRENCIES,
            'payment_method': checkout['payment_method'],
            'payment_methods': PAYMENT_METHODS,
            'rates_source': checkout['rates_source'],
            'rates_updated': checkout['rates_updated'],
            'rate_display': _format_money(checkout['rate'], checkout['currency']),
        })
    except Exception as e:
        import sys
        print(f'Error loading inventory: {e}', file=sys.stderr)
        # Fall back to basic inventory view with default currency
        products = Product.objects.prefetch_related(
            Prefetch('images', queryset=ProductImage.objects.all())
        ).all()
        inventory_items = []
        for product in products:
            product_images = list(product.images.all())
            image_url = _product_image_url(product_images[0].image) if product_images else ''
            inventory_items.append({
                'product': product,
                'price_display': str(product.price),
                'image_url': image_url,
            })
        return render(request, 'core/inventory.html', {
            'inventory_items': inventory_items,
            'currency': 'USD',
            'supported_currencies': SUPPORTED_CURRENCIES,
            'payment_method': 'mtn',
            'payment_methods': PAYMENT_METHODS,
            'rates_source': 'fallback',
            'rates_updated': '',
            'rate_display': '1.00',
        })


@require_POST
def add_to_cart(request, product_id):
    product = Product.objects.get(id=product_id)
    size = request.POST.get('size', '')
    quantity = int(request.POST.get('quantity', 1))
    color = product.color
    available_sizes = product.size_list()

    if available_sizes and size not in available_sizes:
        messages.error(request, 'Please choose one of the listed EU sizes before adding this item to cart.')
        return redirect('inventory')

    cart = _current_cart(request, create=True)
    item, created = CartItem.objects.get_or_create(cart=cart, product=product, size=size, color=color)

    if not created:
        item.quantity += quantity
    else:
        item.quantity = quantity

    item.save()
    return HttpResponseRedirect(reverse('cart'))


def cart(request):
    try:
        checkout = _checkout_preferences(request)
        cart = _current_cart(request, create=False)
        items = []
        items_view = []
        grand_total = Decimal('0')

        if cart:
            items = cart.items.select_related('product')

        for item in items:
            base_price = _safe_decimal(item.product.price, Decimal('0'))
            line_total_base = base_price * item.quantity
            line_total = line_total_base * checkout['rate']
            grand_total += line_total
            items_view.append({
                'item': item,
                'price_display': _format_money(base_price * checkout['rate'], checkout['currency']),
                'line_total_display': _format_money(line_total, checkout['currency']),
            })

        return render(request, 'core/cart.html', {
            'cart': cart,
            'items': items,
            'items_view': items_view,
            'currency': checkout['currency'],
            'supported_currencies': SUPPORTED_CURRENCIES,
            'payment_method': checkout['payment_method'],
            'payment_methods': PAYMENT_METHODS,
            'grand_total_display': _format_money(grand_total, checkout['currency']),
            'rates_source': checkout['rates_source'],
            'rates_updated': checkout['rates_updated'],
            'rate_display': _format_money(checkout['rate'], checkout['currency']),
        })
    except Exception as e:
        import sys
        print(f'Error loading cart: {e}', file=sys.stderr)
        # Fall back to basic cart view with default currency
        cart = _current_cart(request, create=False)
        items = []
        items_view = []
        grand_total = Decimal('0')
        
        if cart:
            items = cart.items.select_related('product')
            for item in items:
                base_price = _safe_decimal(item.product.price, Decimal('0'))
                line_total = base_price * item.quantity
                grand_total += line_total
                items_view.append({
                    'item': item,
                    'price_display': str(base_price),
                    'line_total_display': str(line_total),
                })

        return render(request, 'core/cart.html', {
            'cart': cart,
            'items': items,
            'items_view': items_view,
            'currency': 'USD',
            'supported_currencies': SUPPORTED_CURRENCIES,
            'payment_method': 'mtn',
            'payment_methods': PAYMENT_METHODS,
            'grand_total_display': str(grand_total),
            'rates_source': 'fallback',
            'rates_updated': '',
            'rate_display': '1.00',
        })


def checkout(request):
    cart = _current_cart(request, create=False)
    if not cart or not cart.items.exists():
        messages.info(request, 'Your cart is empty. Add items before checkout.')
        return redirect('cart')

    checkout_prefs = _checkout_preferences(request)
    cart_items = list(cart.items.select_related('product'))

    items_view = []
    grand_total = Decimal('0')
    for item in cart_items:
        base_price = _safe_decimal(item.product.price, Decimal('0'))
        unit_price = base_price * checkout_prefs['rate']
        line_total = unit_price * item.quantity
        grand_total += line_total
        items_view.append({
            'name': item.product.name,
            'quantity': item.quantity,
            'size': item.size,
            'color': item.color,
            'unit_price_display': _format_money(unit_price, checkout_prefs['currency']),
            'line_total_display': _format_money(line_total, checkout_prefs['currency']),
        })

    context = {
        'items_view': items_view,
        'currency': checkout_prefs['currency'],
        'payment_method': checkout_prefs['payment_method'],
        'grand_total_display': _format_money(grand_total, checkout_prefs['currency']),
        'form_data': {
            'name': '',
            'phone': '',
            'country': '',
            'notes': '',
        },
    }

    if request.method == 'POST':
        form_data = {
            'name': (request.POST.get('name') or '').strip(),
            'phone': (request.POST.get('phone') or '').strip(),
            'country': (request.POST.get('country') or '').strip(),
            'notes': (request.POST.get('notes') or '').strip(),
        }
        context['form_data'] = form_data

        if not form_data['name'] or not form_data['phone'] or not form_data['country']:
            messages.error(request, 'Name, phone, and country are required to place your order.')
            return render(request, 'core/checkout.html', context)

        with transaction.atomic():
            order = Order.objects.create(
                user=request.user if request.user.is_authenticated else None,
                session_key=request.session.session_key,
                customer_name=form_data['name'],
                phone=form_data['phone'],
                country=form_data['country'],
                notes=form_data['notes'],
                payment_method=checkout_prefs['payment_method'],
                currency=checkout_prefs['currency'],
                total_amount=grand_total.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
            )

            for item in cart_items:
                unit_price = (_safe_decimal(item.product.price, Decimal('0')) * checkout_prefs['rate']).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                line_total = (unit_price * item.quantity).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                OrderItem.objects.create(
                    order=order,
                    product_name=item.product.name,
                    quantity=item.quantity,
                    size=item.size,
                    color=item.color,
                    unit_price=unit_price,
                    line_total=line_total,
                )

            # Clear the cart after a successful order capture.
            cart.items.all().delete()

        return render(request, 'core/checkout_success.html', {
            'order': order,
            'currency': checkout_prefs['currency'],
            'grand_total_display': _format_money(grand_total, checkout_prefs['currency']),
            'payment_method': checkout_prefs['payment_method'],
            'instructions': _payment_instructions(form_data['country'], checkout_prefs['payment_method']),
        })

    return render(request, 'core/checkout.html', context)


@require_POST
def update_cart_item(request, item_id):
    cart = _current_cart(request, create=False)
    if not cart:
        return redirect('cart')

    item = get_object_or_404(CartItem, id=item_id, cart=cart)
    quantity = int(request.POST.get('quantity', 1))
    if quantity > 0:
        item.quantity = quantity
        item.save()
    else:
        item.delete()
    return redirect('cart')


@require_POST
def remove_cart_item(request, item_id):
    cart = _current_cart(request, create=False)
    if not cart:
        return redirect('cart')

    item = get_object_or_404(CartItem, id=item_id, cart=cart)
    item.delete()
    return redirect('cart')
