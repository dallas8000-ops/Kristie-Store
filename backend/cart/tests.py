from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from inventory.models import Category, Product

from .models import CartItem


class CartFlowSmokeTests(TestCase):
	def setUp(self):
		category = Category.objects.create(name='Shoes', description='Footwear')
		self.product = Product.objects.create(
			name='Runner',
			description='Lightweight running shoe',
			price=Decimal('49.99'),
			category=category,
			color='Black',
			in_stock=True,
		)

	def test_cart_page_loads(self):
		response = self.client.get(reverse('cart'))
		self.assertEqual(response.status_code, 200)

	def test_add_to_cart_creates_item(self):
		response = self.client.post(
			reverse('add_to_cart', args=[self.product.id]),
			data={'quantity': 2, 'size': 'M'},
			follow=True,
		)
		self.assertEqual(response.status_code, 200)
		self.assertEqual(CartItem.objects.count(), 1)
		item = CartItem.objects.select_related('product').first()
		self.assertEqual(item.product_id, self.product.id)
		self.assertEqual(item.quantity, 2)
