import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "audit_agent.settings")

import django

django.setup()

from indicators.services.recommendation import get_fund_usage_recommendations


class FundUsageRecommendationServiceTests(unittest.TestCase):
    def test_empty_query_returns_empty_list(self):
        result = get_fund_usage_recommendations("   ")
        self.assertEqual(result, [])

    def test_no_results_above_threshold_returns_empty_list(self):
        with patch(
            "indicators.services.recommendation.call_begm3_api",
            return_value=[0.1, 0.2],
        ) as mock_embed, patch(
            "indicators.services.recommendation.get_milvus_manager"
        ) as mock_get_manager:
            manager = Mock()
            manager.search_similar_indicators.return_value = [
                {"indicator_id": 1, "score": 0.5},
                {"indicator_id": 2, "score": 0.2},
            ]
            mock_get_manager.return_value = manager

            result = get_fund_usage_recommendations("预算绩效", province_id=11)

        self.assertEqual(result, [])
        mock_embed.assert_called_once_with("预算绩效")
        manager.search_similar_indicators.assert_called_once_with(
            [0.1, 0.2], top_k=200, province_id=11
        )

    def test_recommendations_are_grouped_sorted_and_include_indicators(self):
        with patch(
            "indicators.services.recommendation.call_begm3_api",
            return_value=[0.01, 0.02],
        ) as mock_embed, patch(
            "indicators.services.recommendation.get_milvus_manager"
        ) as mock_get_manager, patch(
            "indicators.services.recommendation.Indicator"
        ) as mock_indicator_model, patch(
            "indicators.services.recommendation.FundUsage"
        ) as mock_fund_usage_model:
            manager = Mock()
            manager.search_similar_indicators.return_value = [
                {"indicator_id": 1, "score": 0.90},
                {"indicator_id": 2, "score": 0.75},
                {"indicator_id": 3, "score": 0.55},
                {"indicator_id": 4, "score": 0.49},
            ]
            mock_get_manager.return_value = manager

            mock_indicator_model.objects.filter.return_value.values_list.return_value = [
                (1, 10),
                (2, 20),
                (3, 10),
                (4, 20),
            ]

            fu_a = SimpleNamespace(
                id=10,
                name="信息化建设",
                province_id=31,
                province=SimpleNamespace(name="上海市"),
            )
            fu_b = SimpleNamespace(
                id=20,
                name="培训提升",
                province_id=None,
                province=None,
            )
            mock_fund_usage_model.objects.filter.return_value = [fu_a, fu_b]

            indicator_a = SimpleNamespace(
                id=1,
                business_code="A-1",
                fund_usage_id=10,
                province_id_id=31,
                level_1="产出指标",
                level_2="数量指标",
                level_3="设备采购数量",
                nature=">=",
                unit="台",
                explanation="采购不少于 20 台",
                is_active=True,
                source_tag="batch-a",
            )
            indicator_b = SimpleNamespace(
                id=2,
                business_code="B-1",
                fund_usage_id=20,
                province_id_id=31,
                level_1="效益指标",
                level_2="社会效益",
                level_3="培训覆盖率",
                nature=">=",
                unit="%",
                explanation="覆盖率不低于 80%",
                is_active=True,
                source_tag="batch-b",
            )

            qs_a = Mock()
            qs_a.select_related.return_value.order_by.return_value = [indicator_a]
            qs_b = Mock()
            qs_b.select_related.return_value.order_by.return_value = [indicator_b]

            def _all_objects_filter(**kwargs):
                self.assertEqual(kwargs["is_active"], True)
                self.assertEqual(kwargs["province_id_id"], 31)
                if kwargs["fund_usage_id"] == 10:
                    return qs_a
                if kwargs["fund_usage_id"] == 20:
                    return qs_b
                raise AssertionError(f"unexpected kwargs: {kwargs}")

            mock_indicator_model.all_objects.filter.side_effect = _all_objects_filter

            results = get_fund_usage_recommendations("  预算绩效目标  ", province_id=31)

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["id"], 10)
        self.assertEqual(results[0]["score"], 1.45)
        self.assertEqual(results[0]["province_name"], "上海市")
        self.assertEqual(results[0]["indicators"][0]["business_code"], "A-1")

        self.assertEqual(results[1]["id"], 20)
        self.assertEqual(results[1]["score"], 0.75)
        self.assertEqual(results[1]["province_name"], "")
        self.assertEqual(results[1]["indicators"][0]["business_code"], "B-1")

        mock_embed.assert_called_once_with("预算绩效目标")
        manager.search_similar_indicators.assert_called_once_with(
            [0.01, 0.02], top_k=200, province_id=31
        )


if __name__ == "__main__":
    unittest.main()
