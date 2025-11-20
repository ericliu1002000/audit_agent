from typing import List, Optional, Union, Literal
from pydantic import BaseModel, Field

class ProjectInfoSchema(BaseModel):
    """
    项目基础信息 (Pydantic Model)
    用于 AI 解析后的结构化输出，非数据库模型。
    """
    project_name: str = Field(..., description="项目名称")
    department: str = Field(..., description="主管预算部门")
    implementation_unit: str = Field(..., description="项目实施单位")
    project_attribute: Optional[str] = Field(None, description="项目属性，如'经常性项目'或'一次性项目'")
    start_date: Optional[str] = Field(None, description="项目开始时间")
    end_date: Optional[str] = Field(None, description="项目结束时间")
    
    # 资金部分 (统一单位：万元)
    total_budget: float = Field(..., description="项目资金总额")
    fiscal_funds: float = Field(..., description="其中：财政拨款金额")
    other_funds: float = Field(0.0, description="其他资金金额")
    
    goal_description: str = Field(..., description="绩效目标完整文本描述")

class IndicatorSchema(BaseModel):
    """
    单条绩效指标 (Pydantic Model)
    涵盖：产出指标、效益指标、满意度指标、成本指标
    """
    level1: str = Field(..., description="一级指标，如'产出指标', '效益指标', '成本指标'")
    level2: Optional[str] = Field(None, description="二级指标，如'数量指标', '质量指标'")
    level3: str = Field(..., description="三级指标/具体指标名称，如'培训人数', '系统维护数量'")
    
    # 核心：数值与符号分离
    # 允许 operator 为 null (针对定性指标)
    operator: Optional[Literal['>=', '<=', '=', '>', '<', 'range']] = Field(None, description="逻辑符号")
    
    # 允许 target_value 为 String (定性指标如'有效提升') 或 Float (定量指标) 或 None
    target_value: Union[float, str, None] = Field(None, description="指标值。如果是'*'或空则为None；如果是文字描述则保留字符串")
    
    unit: Optional[str] = Field(None, description="单位，如'人', '万元', '%', '个'")
    
    raw_text: str = Field(..., description="原始指标值文本，如 '≥95%' 用于人工核对")

class PerformanceDeclarationSchema(BaseModel):
    """整个申报表的数据契约"""
    project_info: ProjectInfoSchema
    indicators: List[IndicatorSchema] = Field(..., description="所有的指标列表")

# ---------------------------------------------------------
# 如果需要生成 JSON Schema 给 DeepSeek Prompt 使用，可以调用此方法
# ---------------------------------------------------------
def get_ai_extraction_schema():
    import json
    # dump_json_schema 是 Pydantic V2 的用法，如果是 V1 用 .schema_json()
    try:
        return json.dumps(PerformanceDeclarationSchema.model_json_schema(), indent=2, ensure_ascii=False)
    except AttributeError:
        # 兼容 Pydantic V1
        return PerformanceDeclarationSchema.schema_json(indent=2, ensure_ascii=False)