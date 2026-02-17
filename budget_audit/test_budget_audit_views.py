import json
from decimal import Decimal
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from budget_audit.models import BudgetPriceItem
from budget_audit.services.normalization import build_embedding_text


User = get_user_model()


class BudgetAuditPageTests(TestCase):
    def setUp(self):
        self.password = "Testpass123"
        self.user = User.objects.create_user(username="tester", password=self.password)
        self.client = Client()

    def test_budget_audit_page_requires_login(self):
        resp = self.client.get(reverse("budget_audit:audit_page"))
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(resp.url.startswith(reverse("user:login")))

    def test_budget_audit_page_renders(self):
        self.client.login(username=self.user.username, password=self.password)
        resp = self.client.get(reverse("budget_audit:audit_page"))
        self.assertContains(resp, "预算审核", status_code=200)

    def test_budget_audit_api_requires_login(self):
        resp = self.client.post(
            reverse("budget_audit:api_budget_audit"),
            data="{}",
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(resp.url.startswith(reverse("user:login")))

    def test_budget_audit_api_rejects_when_no_standard_data(self):
        self.client.login(username=self.user.username, password=self.password)
        resp = self.client.post(
            reverse("budget_audit:api_budget_audit"),
            data=json.dumps(
                {
                    "material_name": "矿渣硅酸盐水泥",
                    "spec_model": "32.5级 散装",
                    "unit": "t",
                    "vendor_price": "382.22",
                    "is_tax_included": True,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("尚未导入政府标准价格清单", resp.json().get("error", ""))

    @patch("budget_audit.services.match_service._judge_candidates_with_deepseek")
    @patch("budget_audit.services.match_service.get_budget_milvus_manager")
    @patch("budget_audit.services.match_service.call_siliconflow_qwen3_embedding_api")
    def test_budget_audit_api_happy_path_uses_latest_batch(
        self, mock_embed, mock_get_manager, mock_judge
    ):
        self.client.login(username=self.user.username, password=self.password)

        old_item = BudgetPriceItem.objects.create(
            material_name="矿渣硅酸盐水泥",
            spec_model="32.5级 散装",
            unit="t",
            base_price=Decimal("380.00"),
            price_low=Decimal("300.00"),
            price_high=Decimal("500.00"),
            is_tax_included=True,
            publish_month="2025-11",
            region="旧批次",
            embedding_text=build_embedding_text(
                material_name="矿渣硅酸盐水泥",
                spec_model="32.5级 散装",
                unit="t",
                is_tax_included=True,
            ),
        )
        latest_item = BudgetPriceItem.objects.create(
            material_name="矿渣硅酸盐水泥",
            spec_model="32.5级 散装",
            unit="t",
            base_price=Decimal("382.22"),
            price_low=Decimal("285.80"),
            price_high=Decimal("515.00"),
            is_tax_included=True,
            publish_month="2025-12",
            region="最新批次",
            embedding_text=build_embedding_text(
                material_name="矿渣硅酸盐水泥",
                spec_model="32.5级 散装",
                unit="t",
                is_tax_included=True,
            ),
        )

        mock_embed.return_value = [0.1, 0.2, 0.3]
        manager = Mock()
        manager.search_candidates.return_value = [
            {"item_id": old_item.id, "score": 0.91},
            {"item_id": latest_item.id, "score": 0.89},
        ]
        mock_get_manager.return_value = manager

        mock_judge.return_value = {
            "judgement": "一致",
            "matched_id": latest_item.id,
            "reason": "名称、规格与口径一致",
            "confidence": 0.92,
            "sentence": "建议匹配矿渣硅酸盐水泥 32.5级 散装；结论：一致。",
        }

        resp = self.client.post(
            reverse("budget_audit:api_budget_audit"),
            data=json.dumps(
                {
                    "material_name": "32.5级矿渣水泥",
                    "spec_model": "32.5级 散装",
                    "unit": "t",
                    "vendor_price": "390.00",
                    "is_tax_included": True,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data.get("judgement"), "一致")
        self.assertEqual(data.get("sentence"), mock_judge.return_value["sentence"])
        self.assertEqual(data.get("matched_item", {}).get("id"), latest_item.id)

        candidate_ids = [c.get("id") for c in (data.get("candidates") or [])]
        self.assertIn(latest_item.id, candidate_ids)
        self.assertNotIn(old_item.id, candidate_ids)

