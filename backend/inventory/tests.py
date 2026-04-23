from decimal import Decimal

from django.urls import reverse
from rest_framework.test import APITestCase

from .models import Category, Product


class InventoryApiSmokeTests(APITestCase):
	def setUp(self):
		self.category = Category.objects.create(name='Shirts', description='Top wear')
		Product.objects.create(
			name='Classic Tee',
			description='Cotton t-shirt',
			price=Decimal('19.99'),
			category=self.category,
			in_stock=True,
		)

	def test_products_endpoint_returns_ok_and_data(self):
		response = self.client.get(reverse('product-list'))
		self.assertEqual(response.status_code, 200)
		self.assertGreaterEqual(len(response.data), 1)

	def test_categories_endpoint_returns_ok_and_data(self):
		response = self.client.get(reverse('category-list'))
		self.assertEqual(response.status_code, 200)
		self.assertGreaterEqual(len(response.data), 1)
