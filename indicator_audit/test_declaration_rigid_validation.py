import unittest

from indicator_audit.services.declaration.rigid_validation import (
    parse_flexible_date,
    run_rigid_validation,
)
from indicator_audit.services.declaration.schemas import PerformanceDeclarationSchema


def _build_payload():
    return {
        "project_info": {
            "project_name": "智慧校园建设",
            "department": "教育局",
            "implementation_unit": "信息中心",
            "project_attribute": "经常性项目",
            "start_date": "2025-01-01",
            "end_date": "2025-12-31",
            "total_budget": 100.0,
            "fiscal_funds": 70.0,
            "other_funds": 30.0,
            "goal_description": "提升校园信息化治理能力",
        },
        "indicators": [
            {
                "level1": "产出指标",
                "level2": "数量指标",
                "level3": "设备采购数量",
                "operator": ">=",
                "target_value": 20,
                "unit": "台",
                "raw_text": "≥20台",
            },
            {
                "level1": "效益指标",
                "level2": "社会效益",
                "level3": "家长满意度",
                "operator": ">=",
                "target_value": 85,
                "unit": "%",
                "raw_text": "≥85%",
            },
            {
                "level1": "满意度指标",
                "level2": "服务对象满意度",
                "level3": "师生满意度",
                "operator": ">=",
                "target_value": 90,
                "unit": "%",
                "raw_text": "≥90%",
            },
        ],
    }


class DeclarationRigidValidationTests(unittest.TestCase):
    def test_parse_flexible_date_supports_multiple_formats(self):
        self.assertEqual(parse_flexible_date("2026年1月").strftime("%Y-%m-%d"), "2026-01-01")
        self.assertEqual(parse_flexible_date("2026/01/03").strftime("%Y-%m-%d"), "2026-01-03")
        self.assertEqual(parse_flexible_date("26-05-15").strftime("%Y-%m-%d"), "2026-05-15")

    def test_run_rigid_validation_detects_core_errors(self):
        payload = _build_payload()
        payload["project_info"]["project_name"] = ""
        payload["project_info"]["department"] = ""
        payload["project_info"]["goal_description"] = ""
        payload["project_info"]["total_budget"] = 100.0
        payload["project_info"]["fiscal_funds"] = 60.0
        payload["project_info"]["other_funds"] = 30.0
        payload["indicators"] = [
            {
                "level1": "产出指标",
                "level2": "数量指标",
                "level3": "设备采购数量",
                "operator": ">=",
                "target_value": "*",
                "unit": "台",
                "raw_text": "*",
            }
        ]
        data = PerformanceDeclarationSchema.model_validate(payload)

        issues = run_rigid_validation(data)
        messages = [issue["msg"] for issue in issues]

        self.assertTrue(any("项目名称未填写" in msg for msg in messages))
        self.assertTrue(any("主管预算部门未填写" in msg for msg in messages))
        self.assertTrue(any("绩效目标描述未填写" in msg for msg in messages))
        self.assertTrue(any("资金总额" in msg and "不符" in msg for msg in messages))
        self.assertTrue(any("缺少以下维度" in msg for msg in messages))
        self.assertTrue(any("占位符" in msg for msg in messages))

    def test_run_rigid_validation_checks_time_logic(self):
        payload = _build_payload()
        payload["project_info"]["start_date"] = "2025年12月"
        payload["project_info"]["end_date"] = "2025年1月"
        payload["indicators"].append(
            {
                "level1": "产出指标",
                "level2": "时效指标",
                "level3": "建设完成时间",
                "operator": "=",
                "target_value": "2026年12月",
                "unit": "月",
                "raw_text": "2026年12月",
            }
        )
        data = PerformanceDeclarationSchema.model_validate(payload)

        issues = run_rigid_validation(data)
        messages = [issue["msg"] for issue in issues]

        self.assertTrue(any("结束时间早于开始时间" in msg for msg in messages))
        self.assertTrue(any("晚于项目结束时间" in msg for msg in messages))


if __name__ == "__main__":
    unittest.main()
