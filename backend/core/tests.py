from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class AuthRouteSmokeTests(TestCase):
    def test_login_page_loads(self):
        response = self.client.get(reverse('login'))
        self.assertEqual(response.status_code, 200)

    def test_signup_page_loads(self):
        response = self.client.get(reverse('signup'))
        self.assertEqual(response.status_code, 200)

    def test_signup_creates_user_and_redirects(self):
        response = self.client.post(
            reverse('signup'),
            data={
                'username': 'newuser',
                'password1': 'StrongPass123!',
                'password2': 'StrongPass123!',
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(get_user_model().objects.filter(username='newuser').count(), 1)
