from django.contrib.auth import get_user_model
from django.urls import reverse
from django.test import Client, TestCase


User = get_user_model()


class AuthFlowTests(TestCase):
    def setUp(self):
        self.password = 'Testpass123'
        self.user = User.objects.create_user(username='tester', password=self.password)
        self.client = Client()

    def test_login_success_flow(self):
        response = self.client.post(reverse('user:login'), {
            'username': self.user.username,
            'password': self.password,
        })
        self.assertRedirects(response, reverse('home'))

    def test_login_invalid_credentials(self):
        response = self.client.post(reverse('user:login'), {
            'username': self.user.username,
            'password': 'wrong',
        })
        self.assertContains(response, '用户名或密码不正确', status_code=200)

    def test_change_password_requires_auth(self):
        response = self.client.get(reverse('user:change-password'))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse('user:login')))

    def test_change_password_flow_logs_out(self):
        self.client.login(username=self.user.username, password=self.password)
        new_password = 'Newpass456'
        response = self.client.post(reverse('user:change-password'), {
            'old_password': self.password,
            'new_password1': new_password,
            'new_password2': new_password,
        })
        self.assertRedirects(response, reverse('user:login'))
        # Should be logged out now
        response = self.client.get(reverse('user:change-password'))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse('user:login')))
        # Ensure new password works
        self.assertTrue(self.client.login(username=self.user.username, password=new_password))

    def test_forgot_password_flow(self):
        self.client.login(username=self.user.username, password=self.password)
        new_password = 'AnotherPass789'
        response = self.client.post(reverse('user:forgot-password'), {
            'old_password': self.password,
            'new_password1': new_password,
            'new_password2': new_password,
        })
        self.assertRedirects(response, reverse('user:login'))
        # After reset, should be forced to login again
        response = self.client.get(reverse('user:change-password'))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse('user:login')))
        self.assertTrue(self.client.login(username=self.user.username, password=new_password))
