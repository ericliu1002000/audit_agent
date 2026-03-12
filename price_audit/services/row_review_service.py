"""价格审核逐行审核服务。"""

from __future__ import annotations

from decimal import Decimal

from price_audit.agent import review_row_with_agent
from price_audit.models import PriceAuditRowDecision, PriceAuditSubmissionRow
from price_audit.services.normalization import parse_decimal


ZERO = Decimal("0")


def _calculate_amount(
    unit_price: Decimal | None,
    quantity: Decimal | None,
    days: Decimal | None,
) -> Decimal | None:
    """尽量依据单价、数量、天数重算金额。"""

    factors = [item for item in (unit_price, quantity, days) if item is not None]
    if not factors:
        return None
    amount = Decimal("1")
    for factor in factors:
        amount *= factor
    return amount


def _same_decimal(left: Decimal | None, right: Decimal | None) -> bool:
    if left is None and right is None:
        return True
    return left == right


def review_leaf_row(submission_row: PriceAuditSubmissionRow) -> PriceAuditRowDecision:
    """审核一条明细行并保存结果。"""

    decision, _ = PriceAuditRowDecision.objects.update_or_create(
        submission_row=submission_row,
        defaults={
            "status": PriceAuditRowDecision.Status.PROCESSING,
            "result_type": "",
            "error_message": "",
        },
    )
    try:
        agent_output, evidence_json = review_row_with_agent(submission_row)
        reviewed_unit = agent_output.reviewed_unit or submission_row.submitted_unit
        reviewed_unit_price = parse_decimal(agent_output.reviewed_unit_price)
        if reviewed_unit_price is None:
            reviewed_unit_price = submission_row.submitted_unit_price
        reviewed_quantity = parse_decimal(agent_output.reviewed_quantity)
        if reviewed_quantity is None:
            reviewed_quantity = submission_row.submitted_quantity
        reviewed_days = parse_decimal(agent_output.reviewed_days)
        if reviewed_days is None:
            reviewed_days = submission_row.submitted_days
        reviewed_amount = parse_decimal(agent_output.reviewed_amount)
        if reviewed_amount is None:
            reviewed_amount = _calculate_amount(
                reviewed_unit_price,
                reviewed_quantity,
                reviewed_days,
            )
        if reviewed_amount is None:
            reviewed_amount = submission_row.submitted_amount

        submitted_amount = submission_row.submitted_amount
        reduction_amount = ZERO
        if submitted_amount is not None and reviewed_amount is not None:
            reduction_amount = submitted_amount - reviewed_amount

        changed = any(
            [
                reviewed_unit != (submission_row.submitted_unit or ""),
                not _same_decimal(reviewed_unit_price, submission_row.submitted_unit_price),
                not _same_decimal(reviewed_quantity, submission_row.submitted_quantity),
                not _same_decimal(reviewed_days, submission_row.submitted_days),
                not _same_decimal(reviewed_amount, submission_row.submitted_amount),
            ]
        )

        decision.status = PriceAuditRowDecision.Status.COMPLETED
        decision.result_type = (
            PriceAuditRowDecision.ResultType.ADJUSTED
            if changed
            else PriceAuditRowDecision.ResultType.UNCHANGED
        )
        decision.reviewed_unit = reviewed_unit
        decision.reviewed_unit_price = reviewed_unit_price
        decision.reviewed_quantity = reviewed_quantity
        decision.reviewed_days = reviewed_days
        decision.reviewed_amount = reviewed_amount
        decision.reduction_amount = reduction_amount
        decision.reason = agent_output.reason.strip()
        decision.evidence_json = evidence_json
        decision.error_message = ""
        decision.save()
        return decision
    except Exception as exc:
        decision.status = PriceAuditRowDecision.Status.FAILED
        decision.result_type = ""
        decision.reviewed_unit = ""
        decision.reviewed_unit_price = None
        decision.reviewed_quantity = None
        decision.reviewed_days = None
        decision.reviewed_amount = None
        decision.reduction_amount = None
        decision.reason = ""
        decision.evidence_json = {}
        decision.error_message = str(exc)
        decision.save()
        return decision
