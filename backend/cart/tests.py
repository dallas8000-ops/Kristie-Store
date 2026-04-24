from decimal import Decimal
from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from inventory.models import Category, Product

from .models import Cart, CartItem, Order, OrderItem


class CartFlowSmokeTests(TestCase):
	def setUp(self):
		category = Category.objects.create(name='Shoes', description='Footwear')
		self.product = Product.objects.create(
			name='Runner',
			description='Lightweight running shoe',
			price=Decimal('49.99'),
			category=category,
			color='Black',
			sizes='32,34,36',
			in_stock=True,
		)

	def test_cart_page_loads(self):
		response = self.client.get(reverse('cart'))
		self.assertEqual(response.status_code, 200)

	def test_add_to_cart_creates_item(self):
		response = self.client.post(
			reverse('add_to_cart', args=[self.product.id]),
			data={'quantity': 2, 'size': '34'},
			follow=True,
		)
		self.assertEqual(response.status_code, 200)
		self.assertEqual(CartItem.objects.count(), 1)
		item = CartItem.objects.select_related('product').first()
		self.assertEqual(item.product_id, self.product.id)
		self.assertEqual(item.quantity, 2)
		self.assertEqual(item.size, '34')

	def test_add_to_cart_rejects_invalid_size(self):
		response = self.client.post(
			reverse('add_to_cart', args=[self.product.id]),
			data={'quantity': 1, 'size': 'XL'},
		)
		self.assertEqual(response.status_code, 302)
		self.assertEqual(response.url, reverse('inventory'))
		self.assertEqual(CartItem.objects.count(), 0)

	def test_checkout_creates_order_and_clears_cart(self):
		self.client.post(
			reverse('add_to_cart', args=[self.product.id]),
			data={'quantity': 2, 'size': '34'},
		)

		response = self.client.post(
			reverse('checkout'),
			data={
				'name': 'Barney Tester',
				'phone': '+256700000000',
				'country': 'Uganda',
				'notes': 'Deliver after 5 PM',
			},
		)

		self.assertEqual(response.status_code, 200)
		self.assertEqual(Order.objects.count(), 1)
		self.assertEqual(OrderItem.objects.count(), 1)
		self.assertEqual(CartItem.objects.count(), 0)

	def test_cart_view_cleans_stale_empty_guest_carts(self):
		stale = Cart.objects.create(user=None, session_key='old-empty')
		Cart.objects.filter(id=stale.id).update(created_at=timezone.now() - timedelta(days=8))

		active = Cart.objects.create(user=None, session_key='active-cart')
		CartItem.objects.create(cart=active, product=self.product, quantity=1, size='34', color='Black')

		response = self.client.get(reverse('cart'))
		self.assertEqual(response.status_code, 200)
		self.assertFalse(Cart.objects.filter(id=stale.id).exists())
		self.assertTrue(Cart.objects.filter(id=active.id).exists())
