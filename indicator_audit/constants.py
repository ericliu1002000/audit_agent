"""
indicator_audit constants
-------------------------
存放审核相关的枚举常量与元数据，便于后端与前端共享统一配置。
"""

# 问题类型（业务大类）
ISSUE_TYPE_COMPLETENESS = "completeness"
ISSUE_TYPE_COMPLIANCE = "compliance"
ISSUE_TYPE_MEASURABILITY = "measurability"
ISSUE_TYPE_RELEVANCE = "relevance"
ISSUE_TYPE_MISMATCH = "mismatch"

ISSUE_TYPE_CHOICES = (
    (ISSUE_TYPE_COMPLETENESS, "完整性缺失"),
    (ISSUE_TYPE_COMPLIANCE, "合规性问题"),
    (ISSUE_TYPE_MEASURABILITY, "可衡量性不足"),
    (ISSUE_TYPE_RELEVANCE, "相关性缺失"),
    (ISSUE_TYPE_MISMATCH, "投入产出不匹配"),
)

SEVERITY_CRITICAL = "critical"
SEVERITY_WARNING = "warning"
SEVERITY_INFO = "info"
SEVERITY_CHOICES = (
    (SEVERITY_CRITICAL, "红灯"),
    (SEVERITY_WARNING, "黄灯"),
    (SEVERITY_INFO, "蓝灯"),
)

# 用于前端展示定义与典型场景
ISSUE_TYPE_DEFINITIONS = {
    ISSUE_TYPE_COMPLETENESS: {
        "label": "完整性缺失 (Completeness)",
        "definition": "申报表的核心要素填写不全，或缺少必要的指标维度，导致信息结构残缺。",
        "examples": [
            "必填项留白（如未填项目名称）",
            "缺少某类核心指标（如只有产出指标，缺效益指标）",
            "单元格中仍保留模板默认的占位符（如 *、XXX）",
        ],
    },
    ISSUE_TYPE_COMPLIANCE: {
        "label": "合规性问题 (Compliance)",
        "definition": "数据违反了明确的数学逻辑、时间逻辑或业务硬性规定，属于“硬伤”类错误。",
        "examples": [
            "资金总额与分项之和不相等",
            "项目结束时间早于开始时间",
            "百分比数值异常（如 120%）",
            "成本指标使用了不允许的符号（如使用“≥”设置下限）",
        ],
    },
    ISSUE_TYPE_MEASURABILITY: {
        "label": "可衡量性不足 (Measurability)",
        "definition": "指标描述模糊、定性词汇过多，缺乏明确的量化标准或验证手段，导致后期无法有效考核。",
        "examples": [
            "大量使用“进一步加强”“有效提升”等词汇却无具体数值",
            "填写了数值但缺失计量单位",
        ],
    },
    ISSUE_TYPE_RELEVANCE: {
        "label": "相关性缺失 (Relevance)",
        "definition": "指标内容与项目绩效目标脱节，无法支撑目标的实现，存在“文不对题”的现象。",
        "examples": [
            "目标强调“设备采购”，指标里却只写“系统维护”",
            "目标提及某项具体工作，但在指标中完全找不到对应考核项",
        ],
    },
    ISSUE_TYPE_MISMATCH: {
        "label": "投入产出不匹配 (Mismatch)",
        "definition": "项目属性、资金投入与设定的指标类型不匹配，存在逻辑上的矛盾或成本超支风险。",
        "examples": [
            "项目属性为“一次性建设”，指标却多为“长期运维”类",
            "分项成本指标的累计金额超过了项目总预算",
        ],
    },
}

