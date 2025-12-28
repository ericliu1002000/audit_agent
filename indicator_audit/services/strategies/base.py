from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Type

from pydantic import BaseModel


class BaseAuditStrategy(ABC):
    """
    审核策略抽象基类：定义不同业务文档必须实现的审核能力。
    """

    @property
    @abstractmethod
    def schema_cls(self) -> Type[BaseModel]:
        """
        功能说明:
            返回当前策略的 Pydantic Schema 类型，用于约束结构化数据。
        输入参数:
            无。
        输出参数:
            Type[BaseModel]: 本策略对应的 Schema 类型。
        """

    @abstractmethod
    def extract_data(self, markdown_text: str) -> BaseModel:
        """
        功能说明:
            将 Excel 转换后的 Markdown 文本解析为结构化数据实例。
        输入参数:
            markdown_text: Excel 转 Markdown 后的文本内容。
        输出参数:
            BaseModel: 按 schema_cls 约束的结构化数据对象。
        """

    @abstractmethod
    def run_rigid_validation(self, data: BaseModel) -> List[Dict[str, Any]]:
        """
        功能说明:
            执行刚性规则校验，输出可被统一报告格式化的原始问题列表。
        输入参数:
            data: 结构化数据对象（应为 schema_cls 的实例）。
        输出参数:
            List[Dict[str, Any]]: 刚性规则问题列表，元素为字典结构。
        """

    @abstractmethod
    def run_semantic_check(self, data: BaseModel) -> List[Dict[str, Any]]:
        """
        功能说明:
            执行语义/逻辑校验，输出可被统一报告格式化的原始问题列表。
        输入参数:
            data: 结构化数据对象（应为 schema_cls 的实例）。
        输出参数:
            List[Dict[str, Any]]: 语义校验问题列表，元素为字典结构。
        """
