

from django.contrib import admin
from .models import Category, Product, ProductImage
from .pricing import apply_price_suggestion, suggest_price_for_product


def _generated_catalog_description(product):
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

class ProductImageInline(admin.TabularInline):
	model = ProductImage
	extra = 1

class ProductAdmin(admin.ModelAdmin):
	list_display = ('name', 'category', 'price_usd', 'price_ugx', 'stock_quantity', 'in_stock')
	list_filter = ('category', 'in_stock')
	search_fields = ('name', 'description')
	fieldsets = (
		('Product Information', {
			'fields': ('name', 'category', 'description', 'color', 'stock_quantity', 'in_stock')
		}),
		('Pricing', {
			'fields': ('price_usd', 'price_ugx', 'old_price'),
			'description': 'Set prices in USD and UGX (Ugandan Shilling)'
		}),
		('Sizes', {
			'fields': ('sizes',)
		}),
	)
	inlines = [ProductImageInline]
	actions = ['generate_catalog_descriptions', 'scan_and_apply_price_suggestions']

	@admin.action(description='Generate catalog descriptions (for blank/auto-created only)')
	def generate_catalog_descriptions(self, request, queryset):
		updated = 0
		for product in queryset:
			description = (product.description or '').strip().lower()
			if description and description != 'auto-created from uploaded catalog image.':
				continue
			product.description = _generated_catalog_description(product)
			product.save(update_fields=['description'])
			updated += 1

		if updated == 0:
			self.message_user(request, 'No products were updated. Selected products already have custom descriptions.')
		else:
			self.message_user(request, f'Generated descriptions for {updated} product(s).')

	@admin.action(description='Scan web comparables and apply suggested prices')
	def scan_and_apply_price_suggestions(self, request, queryset):
		updated = 0
		skipped = 0

		for product in queryset.select_related('category'):
			suggestion = suggest_price_for_product(product)

			if suggestion.price_usd is None:
				skipped += 1
				continue

			if suggestion.confidence < 0.45:
				skipped += 1
				continue

			if apply_price_suggestion(product, suggestion):
				updated += 1

		if updated == 0:
			self.message_user(
				request,
				f'No prices updated. {skipped} product(s) skipped due to low confidence or missing comparable data.'
			)
		else:
			self.message_user(
				request,
				f'Updated prices for {updated} product(s). Skipped {skipped} product(s).'
			)

admin.site.register(Category)
admin.site.register(Product, ProductAdmin)
