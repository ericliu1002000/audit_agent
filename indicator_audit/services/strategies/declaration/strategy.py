from __future__ import annotations

from typing import Any, Dict, List, Type

from pydantic import BaseModel

from indicator_audit.services.declaration.schemas import PerformanceDeclarationSchema
from indicator_audit.services.declaration.ai_extractor_from_md import (
    extract_data_with_ai,
)
from indicator_audit.services.declaration.rigid_validation import (
    run_rigid_validation,
)
from indicator_audit.services.declaration.semantic_validator import (
    run_semantic_check,
)
from indicator_audit.services.strategies.base import BaseAuditStrategy


class DeclarationAuditStrategy(BaseAuditStrategy):
    """
    绩效目标申报表审核策略：将现有申报表的提取与校验逻辑封装为统一接口。
    """

    @property
    def schema_cls(self) -> Type[BaseModel]:
        """
        功能说明:
            返回申报表审核所使用的数据契约 Schema 类型。
        输入参数:
            无。
        输出参数:
            Type[BaseModel]: PerformanceDeclarationSchema 类型。
        """

        return PerformanceDeclarationSchema

    def extract_data(self, markdown_text: str) -> PerformanceDeclarationSchema:
        """
        功能说明:
            从 Markdown 表中抽取结构化申报表数据。
        使用示例:
            strategy = DeclarationAuditStrategy()
            data = strategy.extract_data(markdown_text)
        输入参数:
            markdown_text: Excel 转 Markdown 后的文本内容。
        输出参数:
            PerformanceDeclarationSchema: 结构化后的申报表数据对象。
        """

        return extract_data_with_ai(markdown_text)

    def run_rigid_validation(
        self, data: PerformanceDeclarationSchema
    ) -> List[Dict[str, Any]]:
        """
        功能说明:
            执行申报表的刚性规则校验。
        使用示例:
            issues = strategy.run_rigid_validation(data)
        输入参数:
            data: 结构化后的申报表数据对象。
        输出参数:
            List[Dict[str, Any]]: 刚性校验问题列表。
        """

        return run_rigid_validation(data)

    def run_semantic_check(
        self, data: PerformanceDeclarationSchema
    ) -> List[Dict[str, Any]]:
        """
        功能说明:
            执行申报表的语义校验，输出语义风险提示。
        使用示例:
            semantic_issues = strategy.run_semantic_check(data)
        输入参数:
            data: 结构化后的申报表数据对象。
        输出参数:
            List[Dict[str, Any]]: 语义校验问题列表。
        """

        return run_semantic_check(data)
