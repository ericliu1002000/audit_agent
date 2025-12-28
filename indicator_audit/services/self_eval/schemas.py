from __future__ import annotations

from typing import List, Optional, Union

from pydantic import BaseModel, Field


class SelfEvalProjectInfo(BaseModel):
    """
    项目基础信息（绩效自评表）
    """

    project_name: Optional[str] = Field(None, description="项目名称")
    department: Optional[str] = Field(None, description="市级主管部门")
    implementation_unit: Optional[str] = Field(None, description="项目实施单位")
    year: Optional[str] = Field(None, description="年度")
    overall_goal_target: Optional[str] = Field(None, description="年初预期目标")
    overall_goal_actual: Optional[str] = Field(None, description="年度实际完成情况")


class SelfEvalBudgetItem(BaseModel):
    """
    项目资金（万元）明细行
    """

    item_name: Optional[str] = Field(None, description="资金项名称，如年度资金总额/中央补助")
    year_start_budget: Optional[float] = Field(None, description="年初预算数")
    full_year_budget: Optional[float] = Field(None, description="全年预算数（A）")
    full_year_execution: Optional[float] = Field(None, description="全年执行数（B）")
    score_weight: Optional[float] = Field(None, description="分值")
    self_score: Optional[float] = Field(None, description="得分")
    execution_rate: Optional[float] = Field(None, description="执行率（B/A）")
    deviation_reason: Optional[str] = Field(
        None, description="偏差原因分析及改进措施"
    )


class SelfEvalIndicator(BaseModel):
    """
    绩效指标行
    """

    level1: Optional[str] = Field(None, description="一级指标，如产出指标/效益指标/满意度指标")
    level2: Optional[str] = Field(None, description="二级指标，如数量指标/质量指标")
    level3: Optional[str] = Field(None, description="三级指标/具体指标名称")
    target_value: Union[float, str, None] = Field(
        None, description="年度指标值（A）"
    )
    actual_value: Union[float, str, None] = Field(
        None, description="实际完成值（B）"
    )
    score_weight: Optional[float] = Field(None, description="分值")
    self_score: Optional[float] = Field(None, description="得分")
    deviation_reason: Optional[str] = Field(
        None, description="偏差原因分析及改进措施"
    )


class PerformanceSelfEvalSchema(BaseModel):
    """
    绩效自评表数据契约
    """

    project_info: SelfEvalProjectInfo
    budget_items: List[SelfEvalBudgetItem] = Field(
        default_factory=list, description="项目资金（万元）明细"
    )
    indicators: List[SelfEvalIndicator] = Field(
        default_factory=list, description="绩效指标明细"
    )
    total_weight: Optional[float] = Field(None, description="总分（满分）")
    total_score: Optional[float] = Field(None, description="得分（合计）")
