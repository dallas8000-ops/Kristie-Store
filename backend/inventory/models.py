
from django.core.exceptions import ValidationError
from django.db import models


EU_SIZE_RANGE = tuple(str(size) for size in range(32, 56, 2))
EU_SIZE_SET = set(EU_SIZE_RANGE)


def _normalize_size_token(value):
	cleaned = value.strip().upper()
	if cleaned.startswith('EU '):
		cleaned = cleaned[3:].strip()
	if cleaned not in EU_SIZE_SET:
		raise ValidationError(f'Use EU sizes only. Allowed sizes: {", ".join(EU_SIZE_RANGE)}.')
	return cleaned


def normalize_eu_sizes(value):
	if not value:
		return []

	normalized = []
	for token in value.split(','):
		if not token.strip():
			continue
		size = _normalize_size_token(token)
		if size not in normalized:
			normalized.append(size)

	return sorted(normalized, key=lambda size: EU_SIZE_RANGE.index(size))


def validate_eu_sizes(value):
	normalize_eu_sizes(value)

class Category(models.Model):
	name = models.CharField(max_length=100)
	description = models.TextField(blank=True)

	def __str__(self):
		return self.name


class Product(models.Model):
	name = models.CharField(max_length=200)
	description = models.TextField(blank=True)
	price_usd = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text='Price in USD')
	price_ugx = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text='Price in UGX (Ugandan Shilling)')
	old_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
	category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='products')
	color = models.CharField(max_length=100, blank=True)
	stock_quantity = models.PositiveIntegerField(default=1, help_text='Number of units currently available for sale')
	sizes = models.CharField(
		max_length=200,
		help_text='Comma-separated EU sizes, e.g. 32,34,36,38,40,42,44,46,48,50,52,54',
		blank=True,
		validators=[validate_eu_sizes],
	)
	in_stock = models.BooleanField(default=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	@property
	def price(self):
		"""For backward compatibility, returns USD price"""
		return self.price_usd

	def size_list(self):
		return normalize_eu_sizes(self.sizes)

	def clean(self):
		super().clean()
		if self.sizes:
			self.sizes = ','.join(normalize_eu_sizes(self.sizes))

		if self.stock_quantity == 0:
			self.in_stock = False

	def __str__(self):
		return self.name


class ProductImage(models.Model):
	product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='images')
	image = models.ImageField(upload_to='products/')
	alt_text = models.CharField(max_length=255, blank=True)

	def __str__(self):
		return f"Image for {self.product.name}"
