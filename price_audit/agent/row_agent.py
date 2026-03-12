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
1. 先调用 get_submission_row_context 获取当前行上下文。
2. 如需市场价格依据，调用 search_standard_price_candidates，可多次调用。
3. 如果缺乏可靠证据，优先保持送审值不变，并在 reason 中说明。
4. 输出必须是结构化 JSON，只能包含审核结果，不要输出额外解释。
5. 税费不在本次审核范围内。
""".strip()


def review_row_with_agent(submission_row: PriceAuditSubmissionRow) -> tuple[RowAuditOutput, dict]:
    """调用 LlamaIndex 对单条明细行进行审核。"""

    toolset = PriceAuditToolset(submission_row)
    output = run_function_agent(
        system_prompt=ROW_AGENT_SYSTEM_PROMPT,
        user_prompt=(
            "请审核当前送审行。"
            "先获取当前行上下文，再按需查询标准价候选。"
            "若判断无需审减，请保留原值并给出原因。"
        ),
        tools=[
            toolset.get_submission_row_context,
            toolset.search_standard_price_candidates,
        ],
        output_cls=RowAuditOutput,
    )
    evidence_json = {
        "candidates": toolset.collector.candidates,
        "notes": output.notes,
    }
    return output, evidence_json
