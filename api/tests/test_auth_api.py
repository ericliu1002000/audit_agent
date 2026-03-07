"""认证 API 集成测试。"""

import json

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse


User = get_user_model()


class AuthApiTests(TestCase):
    """覆盖认证接口、自动文档和会话时序。"""

    def setUp(self):
        """初始化测试用户、普通客户端和带 CSRF 校验的客户端。"""

        self.password = "Testpass123"
        self.user = User.objects.create_user(username="tester", password=self.password)
        self.client = Client()
        self.csrf_client = Client(enforce_csrf_checks=True)

        self.schema_url = reverse("api:schema")
        self.swagger_url = reverse("api:docs-swagger")
        self.redoc_url = reverse("api:docs-redoc")
        self.csrf_url = reverse("api:v1:auth-csrf")
        self.login_url = reverse("api:v1:auth-login")
        self.me_url = reverse("api:v1:auth-me")
        self.logout_url = reverse("api:v1:auth-logout")
        self.change_password_url = reverse("api:v1:auth-change-password")

    def _issue_csrf_token(self) -> str:
        """先访问 csrf 接口，拿到后续写请求需要的 token。"""

        response = self.csrf_client.get(self.csrf_url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("csrftoken", response.cookies)
        return response.json()["data"]["csrf_token"]

    def test_schema_endpoint_renders(self):
        """schema 接口应能输出 OpenAPI 文本，并包含会话认证定义。"""

        response = self.client.get(self.schema_url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("application/vnd.oai.openapi", response.headers["Content-Type"])
        schema_text = response.content.decode("utf-8")
        self.assertIn("openapi", schema_text)
        self.assertIn("cookieAuth", schema_text)

    def test_docs_endpoints_render(self):
        """Swagger 和 ReDoc 页面都应该能正常打开。"""

        swagger_response = self.client.get(self.swagger_url)
        redoc_response = self.client.get(self.redoc_url)

        self.assertEqual(swagger_response.status_code, 200)
        self.assertEqual(redoc_response.status_code, 200)

    def test_auth_csrf_returns_token_and_cookie(self):
        """csrf 接口应同时返回 token 和 csrftoken cookie。"""

        response = self.csrf_client.get(self.csrf_url)
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["success"])
        self.assertTrue(payload["data"]["csrf_token"])
        self.assertIn("csrftoken", response.cookies)

    def test_auth_login_requires_csrf(self):
        """未携带 CSRF 的登录请求应被拒绝。"""

        response = self.csrf_client.post(
            self.login_url,
            data=json.dumps(
                {
                    "username": self.user.username,
                    "password": self.password,
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"]["code"], "csrf_failed")

    def test_auth_login_me_and_logout_flow(self):
        """验证登录、获取当前用户、注销的完整会话流程。"""

        csrf_token = self._issue_csrf_token()

        login_response = self.csrf_client.post(
            self.login_url,
            data=json.dumps(
                {
                    "username": self.user.username,
                    "password": self.password,
                }
            ),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertEqual(login_response.status_code, 200)
        login_payload = login_response.json()
        self.assertEqual(login_payload["data"]["user"]["username"], self.user.username)

        me_response = self.csrf_client.get(self.me_url)
        self.assertEqual(me_response.status_code, 200)
        self.assertTrue(me_response.json()["data"]["authenticated"])

        fresh_csrf_token = login_payload["data"]["csrf_token"]
        logout_response = self.csrf_client.post(
            self.logout_url,
            data=json.dumps({}),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=fresh_csrf_token,
        )
        self.assertEqual(logout_response.status_code, 200)
        self.assertFalse(logout_response.json()["data"]["authenticated"])

        me_after_logout = self.csrf_client.get(self.me_url)
        self.assertEqual(me_after_logout.status_code, 401)
        self.assertEqual(
            me_after_logout.json()["error"]["code"],
            "authentication_required",
        )

    def test_auth_change_password_logs_user_out(self):
        """修改密码成功后应强制退出，并允许使用新密码重新登录。"""

        csrf_token = self._issue_csrf_token()
        login_response = self.csrf_client.post(
            self.login_url,
            data=json.dumps(
                {
                    "username": self.user.username,
                    "password": self.password,
                }
            ),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertEqual(login_response.status_code, 200)

        fresh_csrf_token = login_response.json()["data"]["csrf_token"]
        new_password = "Newpass456"
        change_response = self.csrf_client.post(
            self.change_password_url,
            data=json.dumps(
                {
                    "old_password": self.password,
                    "new_password1": new_password,
                    "new_password2": new_password,
                }
            ),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=fresh_csrf_token,
        )
        self.assertEqual(change_response.status_code, 200)
        self.assertFalse(change_response.json()["data"]["authenticated"])

        me_response = self.csrf_client.get(self.me_url)
        self.assertEqual(me_response.status_code, 401)

        self.assertTrue(
            self.client.login(username=self.user.username, password=new_password)
        )
