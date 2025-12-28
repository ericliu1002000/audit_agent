from __future__ import annotations

from typing import Any, Dict, List, Type

from pydantic import BaseModel

from indicator_audit.services.self_eval.ai_extractor_from_md import (
    extract_data_with_ai,
)
from indicator_audit.services.self_eval.rigid_validation import (
    run_rigid_validation,
)
from indicator_audit.services.self_eval.schemas import PerformanceSelfEvalSchema
from indicator_audit.services.self_eval.semantic_validator import (
    run_semantic_check,
)
from indicator_audit.services.strategies.base import BaseAuditStrategy


class SelfEvalAuditStrategy(BaseAuditStrategy):
    """
    绩效自评表审核策略：封装自评表的抽取与校验逻辑。
    """

    @property
    def schema_cls(self) -> Type[BaseModel]:
        """
        功能说明:
            返回自评表审核所使用的数据契约 Schema 类型。
        输入参数:
            无。
        输出参数:
            Type[BaseModel]: PerformanceSelfEvalSchema 类型。
        """

        return PerformanceSelfEvalSchema

    def extract_data(self, markdown_text: str) -> PerformanceSelfEvalSchema:
        """
        功能说明:
            从 Markdown 表中抽取结构化自评表数据。
        使用示例:
            strategy = SelfEvalAuditStrategy()
            data = strategy.extract_data(markdown_text)
        输入参数:
            markdown_text: Excel 转 Markdown 后的文本内容。
        输出参数:
            PerformanceSelfEvalSchema: 结构化后的自评表数据对象。
        """

        return extract_data_with_ai(markdown_text)

    def run_rigid_validation(
        self, data: PerformanceSelfEvalSchema
    ) -> List[Dict[str, Any]]:
        """
        功能说明:
            执行自评表的刚性规则校验。
        使用示例:
            issues = strategy.run_rigid_validation(data)
        输入参数:
            data: 结构化后的自评表数据对象。
        输出参数:
            List[Dict[str, Any]]: 刚性校验问题列表。
        """

        return run_rigid_validation(data)

    def run_semantic_check(
        self, data: PerformanceSelfEvalSchema
    ) -> List[Dict[str, Any]]:
        """
        功能说明:
            执行自评表的语义校验，输出语义风险提示。
        使用示例:
            semantic_issues = strategy.run_semantic_check(data)
        输入参数:
            data: 结构化后的自评表数据对象。
        输出参数:
            List[Dict[str, Any]]: 语义校验问题列表。
        """

        return run_semantic_check(data)
