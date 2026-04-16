"""逐行审核智能体。"""

from __future__ import annotations

from pydantic import BaseModel, Field

from price_audit.agent.tools import PriceAuditToolset
from price_audit.models import PriceAuditSubmissionRow
from utils.agent_runtime.runtime import run_function_agent


class RowAuditOutput(BaseModel):
    """逐行审核的结构化输出。"""

    reviewed_unit: str | None = None
    reviewed_unit_price: str | None = None
    reviewed_quantity: str | None = None
    reviewed_days: str | None = None
    reviewed_amount: str | None = None
    reason: str = ""
    notes: list[str] = Field(default_factory=list)


ROW_AGENT_SYSTEM_PROMPT = """
你是财政价格审核智能体。你只负责审核一条送审费用明细。
要求：
1. 必须先调用 get_submission_row_context。你要先看整单摘要、父项、同组项，再判断当前行。
2. 审核顺序固定为：先判断费用属性，再判断计量口径，再判断价格；禁止跳过前两步直接查价。
3. 费用属性判断顺序固定为：
   - 场馆/政府官方收费
   - 临时展会优先租赁/复用的标准化物品
   - 临时特装的制作类项目
   - 常设陈列的采购/固定安装类项目
   - 人工/运输/服务类
4. 只有确定业务口径后，才可调用 search_standard_price_candidates 查询本地标准价。
5. 价格判断只能基于本地标准价候选；禁止使用联网搜索、公开网页报价或自行臆测市场价。
6. 临时展会默认优先按租赁、复用、模块化口径审核；常设陈列默认优先按耐久采购、固定安装和长期使用口径审核。
7. 包边、收边、踢脚线、压边条默认按 m；板墙、喷绘、地毯、地台面层默认按 ㎡；人工默认按人天；运输默认按次/车次/往返；“项”只能在官方打包项或无法拆量时保留。
8. 要主动识别重复计价风险，如喷绘 vs 工厂制作人工、灯具/布线 vs 电费、运输 vs 搭建打包费。
9. 如果本地标准价证据不足，不要强行审减，应保留送审值，并在 reason 中明确写出“证据不足”。
10. 输出必须是结构化 JSON，只能包含审核结果，不要输出额外解释。
11. 税费不在本次审核范围内。
""".strip()


def review_row_with_agent(submission_row: PriceAuditSubmissionRow) -> tuple[RowAuditOutput, dict]:
    """调用 LlamaIndex 对单条明细行进行审核。"""

    toolset = PriceAuditToolset(submission_row)
    output = run_function_agent(
        system_prompt=ROW_AGENT_SYSTEM_PROMPT,
        user_prompt=(
            "请审核当前送审行。"
            "先获取当前行上下文，必须先判断业务口径和计量单位，再判断价格。"
            "只允许使用本地标准价候选作为价格依据。"
            "若判断无需审减，请保留原值并给出原因。"
        ),
        tools=[
            toolset.get_submission_row_context,
            toolset.search_standard_price_candidates,
        ],
        output_cls=RowAuditOutput,
    )
    evidence_json = toolset.build_evidence_json(
        reviewed_unit_price=output.reviewed_unit_price,
        reviewed_amount=output.reviewed_amount,
        notes=output.notes,
    )
    return output, evidence_json
