import unittest

from indicator_audit.services.self_eval.rigid_validation import run_rigid_validation
from indicator_audit.services.self_eval.schemas import PerformanceSelfEvalSchema


def _build_payload():
    return {
        "project_info": {
            "project_name": "智慧校园建设",
            "department": "教育局",
            "implementation_unit": "信息中心",
            "year": "2025",
            "overall_goal_target": "完成校园信息化改造",
            "overall_goal_actual": "已完成",
        },
        "budget_items": [
            {
                "item_name": "年度资金总额",
                "year_start_budget": 100.0,
                "full_year_budget": 100.0,
                "full_year_execution": 50.0,
                "score_weight": 10.0,
                "self_score": 5.0,
                "execution_rate": 50.0,
                "deviation_reason": "",
            }
        ],
        "indicators": [
            {
                "level1": "产出指标",
                "level2": "数量指标",
                "level3": "设备采购数量",
                "target_value": 100.0,
                "actual_value": 100.0,
                "score_weight": 10.0,
                "self_score": 10.0,
                "deviation_reason": "",
            }
        ],
        "total_weight": 20.0,
        "total_score": 15.0,
    }


class SelfEvalRigidValidationTests(unittest.TestCase):
    def test_budget_execution_score_mismatch_is_detected(self):
        payload = _build_payload()
        payload["budget_items"][0]["self_score"] = 9.0
        data = PerformanceSelfEvalSchema.model_validate(payload)

        issues = run_rigid_validation(data)
        messages = [issue["msg"] for issue in issues]

        self.assertTrue(any("预算执行率得分不匹配" in msg for msg in messages))

    def test_indicator_score_and_missing_reason_are_detected(self):
        payload = _build_payload()
        payload["indicators"][0]["actual_value"] = 80.0
        payload["indicators"][0]["self_score"] = 10.0
        payload["indicators"][0]["deviation_reason"] = ""
        data = PerformanceSelfEvalSchema.model_validate(payload)

        issues = run_rigid_validation(data)
        messages = [issue["msg"] for issue in issues]

        self.assertTrue(any("指标得分不匹配" in msg for msg in messages))
        self.assertTrue(any("未填写偏差原因" in msg for msg in messages))

    def test_valid_payload_produces_no_issues(self):
        payload = _build_payload()
        data = PerformanceSelfEvalSchema.model_validate(payload)

        issues = run_rigid_validation(data)
        self.assertEqual(issues, [])


if __name__ == "__main__":
    unittest.main()
