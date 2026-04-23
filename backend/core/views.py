from pathlib import Path
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import json
import urllib.request

from django.conf import settings
from django.contrib.auth import login, logout
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib import messages
from django.core.mail import send_mail
from django.db.models import Prefetch
from django.http import FileResponse, Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from cart.models import Cart, CartItem
from inventory.models import Product, ProductImage
from pages.forms import ContactInquiryForm
from pages.models import ContactInquiry


SUPPORTED_IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.webp'}
SUPPORTED_CURRENCIES = ('USD', 'EUR', 'KES', 'UGX')
PAYMENT_METHODS = ('mtn', 'airtel', 'pesapal')
FALLBACK_RATES = {
    'USD': Decimal('1'),
    'EUR': Decimal('0.92'),
    'KES': Decimal('129.50'),
    'UGX': Decimal('3820'),
}


def _workspace_images_dir():
    return Path(settings.BASE_DIR).parent / 'images'


def _ensure_session_key(request):
    if not request.session.session_key:
        request.session.create()
    return request.session.session_key


def _current_cart(request, create=False):
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
            'image_url': images[0].image.url,
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
        # Increase timeout to 8 seconds for production environments
        with urllib.request.urlopen(url, timeout=8) as response:
            payload = json.loads(response.read().decode('utf-8'))
        rates = {
            'USD': Decimal('1'),
            'EUR': _safe_decimal(payload.get('rates', {}).get('EUR'), FALLBACK_RATES['EUR']),
            'KES': _safe_decimal(payload.get('rates', {}).get('KES'), FALLBACK_RATES['KES']),
            'UGX': _safe_decimal(payload.get('rates', {}).get('UGX'), FALLBACK_RATES['UGX']),
        }
        return rates, payload.get('date', ''), 'live'
    except Exception as e:
        # Log the error for debugging, but always fall back gracefully
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
            'primary_url': primary_image.image.url,
            'detail_url': detail_image.image.url,
        })

    return render(request, 'core/catalog.html', {
        'catalog_items': catalog_items,
        'total_items': len(catalog_items),
    })


def catalog_image(_request, image_name):
    base_dir = _workspace_images_dir().resolve()
    image_path = (base_dir / image_name).resolve()

    if base_dir not in image_path.parents:
        raise Http404('Invalid image path.')

    if not image_path.exists() or image_path.suffix.lower() not in SUPPORTED_IMAGE_EXTENSIONS:
        raise Http404('Image not found.')

    return FileResponse(open(image_path, 'rb'))


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
            inventory_items.append({
                'product': product,
                'price_display': _format_money(converted_price, checkout['currency']),
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
        inventory_items = [{'product': p, 'price_display': str(p.price)} for p in products]
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


@csrf_exempt
def add_to_cart(request, product_id):
    product = Product.objects.get(id=product_id)
    size = request.POST.get('size', '')
    quantity = int(request.POST.get('quantity', 1))
    color = product.color

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
