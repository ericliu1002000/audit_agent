"""价格审核 Celery 任务。"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Iterable

from celery import shared_task
from django.conf import settings
from django.core.files.base import ContentFile
from django.utils import timezone

from price_audit.models import (
    GovernmentPriceBatch,
    GovernmentPriceItem,
    PriceAuditRowDecision,
    PriceAuditSubmission,
    PriceAuditSubmissionRow,
)
from price_audit.services.export_service import build_audited_excel_content
from price_audit.services.normalization import build_embedding_text
from price_audit.services.report_service import build_submission_report
from price_audit.services.row_review_service import review_leaf_row
from price_audit.services.submission_parser import SUMMARY_FEE_TYPES, populate_submission_rows
from price_audit.vector_store import get_price_audit_milvus_manager
from utils.vector_api import call_siliconflow_qwen3_embedding_api

logger = logging.getLogger(__name__)
ZERO = Decimal("0")


def dispatch_vectorize_government_price_batch(
    batch_id: int,
    deleted_item_ids: Iterable[int] | None = None,
) -> str:
    """提交政府标准价批次向量化任务，并记录排队信息。"""

    deleted_ids = [int(item_id) for item_id in (deleted_item_ids or [])]
    async_result = vectorize_government_price_batch.delay(batch_id, deleted_ids)
    GovernmentPriceBatch.objects.filter(id=batch_id).update(
        vector_task_id=async_result.id,
        vector_queued_at=timezone.now(),
        vector_started_at=None,
        vectorized_at=None,
        last_error="",
        vector_status=GovernmentPriceBatch.VectorStatus.PENDING,
    )
    return async_result.id


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"countdown": 60},
    max_retries=10,
)
def vectorize_government_price_batch(
    self,
    batch_id: int,
    deleted_item_ids: list[int] | None = None,
) -> None:
    """将一个政府标准价批次异步写入 Milvus。"""

    batch = (
        GovernmentPriceBatch.objects.select_related("uploaded_by")
        .prefetch_related("items")
        .get(id=batch_id)
    )
    manager = get_price_audit_milvus_manager()
    deleted_item_ids = [int(item_id) for item_id in (deleted_item_ids or [])]
    if deleted_item_ids:
        manager.delete_items(deleted_item_ids)
    batch.vector_status = GovernmentPriceBatch.VectorStatus.PROCESSING
    batch.vector_task_id = self.request.id or batch.vector_task_id
    batch.vector_started_at = timezone.now()
    pending_items = list(batch.items.filter(is_vectorized=False).order_by("row_no"))
    batch.vector_total = len(pending_items)
    batch.vector_success = 0
    batch.vector_failed = 0
    batch.last_error = ""
    batch.save(
        update_fields=[
            "vector_status",
            "vector_task_id",
            "vector_started_at",
            "vector_total",
            "vector_success",
            "vector_failed",
            "last_error",
            "updated_at",
        ]
    )

    success_count = 0
    failed_count = 0
    last_error = ""
    expected_dim = int(getattr(settings, "MILVUS_EMBED_DIM", 1024))
    processed_count = 0
    reusable_vectors: dict[str, list[float]] = {}
    vectorized_item_ids: list[int] = []

    for item in pending_items:
        try:
            embedding_text = item.embedding_text or build_embedding_text(
                material_name=item.material_name_normalized,
                spec_model=item.spec_model_raw,
                unit=item.unit_raw,
            )
            vector = reusable_vectors.get(embedding_text)
            if not vector:
                existing = manager.get_item_record(item.id)
                if existing and existing.get("embedding_text") == embedding_text:
                    vector = existing.get("embedding")
                if not vector:
                    reusable = manager.find_reusable_vector(embedding_text)
                    if reusable and reusable.get("embedding"):
                        vector = reusable.get("embedding")
                if not vector:
                    vector = call_siliconflow_qwen3_embedding_api(embedding_text)
                reusable_vectors[embedding_text] = list(vector)
            if len(vector) != expected_dim:
                raise ValueError(
                    f"标准价 {item.id} 向量维度 {len(vector)} 与设定 {expected_dim} 不一致"
                )
            manager.upsert_item(
                item_id=item.id,
                batch_id=batch.id,
                year=batch.year,
                region_name=batch.region_name,
                unit=item.unit_normalized,
                embedding_text=embedding_text,
                vector=vector,
            )
            vectorized_item_ids.append(item.id)
            success_count += 1
        except Exception as exc:  # pragma: no cover - depends on runtime services
            failed_count += 1
            last_error = str(exc)
            logger.exception("标准价 %s 向量化失败: %s", item.id, exc)
        finally:
            processed_count += 1
            should_flush_progress = failed_count > 0 or processed_count % 10 == 0
            if should_flush_progress:
                GovernmentPriceBatch.objects.filter(id=batch.id).update(
                    vector_success=success_count,
                    vector_failed=failed_count,
                    last_error=last_error,
                )

    if vectorized_item_ids:
        GovernmentPriceItem.objects.filter(id__in=vectorized_item_ids).update(is_vectorized=True)

    batch.vector_success = success_count
    batch.vector_failed = failed_count
    batch.vectorized_at = timezone.now()
    batch.last_error = last_error
    batch.vector_status = (
        GovernmentPriceBatch.VectorStatus.ACTIVE
        if failed_count == 0
        else GovernmentPriceBatch.VectorStatus.FAILED
    )
    batch.save(
        update_fields=[
            "vector_success",
            "vector_failed",
            "vector_started_at",
            "vectorized_at",
            "last_error",
            "vector_status",
            "updated_at",
        ]
    )


def dispatch_process_price_audit_submission(submission_id: int) -> str:
    """提交价格审核送审单处理任务。"""

    async_result = process_price_audit_submission.delay(submission_id)
    return async_result.id


def _update_submission_progress(
    submission: PriceAuditSubmission,
    *,
    status: str | None = None,
    current_step: str | None = None,
    progress_percent: int | None = None,
    total_rows: int | None = None,
    processed_rows: int | None = None,
    failed_rows: int | None = None,
    current_message: str | None = None,
    error_message: str | None = None,
    report_json: dict | None = None,
) -> None:
    """更新送审单进度信息。"""

    update_fields: list[str] = []

    if status is not None:
        submission.status = status
        update_fields.append("status")
    if current_step is not None:
        submission.current_step = current_step
        update_fields.append("current_step")
    if progress_percent is not None:
        submission.progress_percent = max(0, min(100, int(progress_percent)))
        update_fields.append("progress_percent")
    if total_rows is not None:
        submission.total_rows = max(0, int(total_rows))
        update_fields.append("total_rows")
    if processed_rows is not None:
        submission.processed_rows = max(0, int(processed_rows))
        update_fields.append("processed_rows")
    if failed_rows is not None:
        submission.failed_rows = max(0, int(failed_rows))
        update_fields.append("failed_rows")
    if current_message is not None:
        submission.current_message = current_message
        update_fields.append("current_message")
    if error_message is not None:
        submission.error_message = error_message
        update_fields.append("error_message")
    if report_json is not None:
        submission.report_json = report_json
        update_fields.append("report_json")

    if not update_fields:
        return

    submission.save(update_fields=[*update_fields, "updated_at"])


def _update_decision(
    row: PriceAuditSubmissionRow,
    *,
    status: str,
    result_type: str,
    reviewed_amount: Decimal | None = None,
    reduction_amount: Decimal | None = None,
    reason: str = "",
    error_message: str = "",
) -> PriceAuditRowDecision:
    """创建或更新一条审核结果。"""

    decision, _ = PriceAuditRowDecision.objects.update_or_create(
        submission_row=row,
        defaults={
            "status": status,
            "result_type": result_type,
            "reviewed_unit": "",
            "reviewed_unit_price": None,
            "reviewed_quantity": None,
            "reviewed_days": None,
            "reviewed_amount": reviewed_amount,
            "reduction_amount": reduction_amount,
            "reason": reason,
            "evidence_json": {},
            "error_message": error_message,
        },
    )
    return decision


def _sum_amounts(decisions: list[PriceAuditRowDecision]) -> Decimal:
    """累加审核金额。"""

    return sum((decision.reviewed_amount or ZERO) for decision in decisions)


def _has_failed_dependency(decisions: list[PriceAuditRowDecision | None]) -> bool:
    """判断依赖项是否存在缺失或失败。"""

    return any(
        decision is None or decision.status == PriceAuditRowDecision.Status.FAILED
        for decision in decisions
    )


def _aggregate_non_leaf_rows(submission: PriceAuditSubmission) -> None:
    """为父项、小计、税费、合计生成程序化审核结果。"""

    rows = list(submission.rows.order_by("excel_row_no"))
    decision_map = {
        decision.submission_row_id: decision
        for decision in PriceAuditRowDecision.objects.filter(
            submission_row__submission=submission
        )
    }

    for row in rows:
        if row.row_type == PriceAuditSubmissionRow.RowType.LEAF:
            continue

        if row.row_type == PriceAuditSubmissionRow.RowType.SUMMARY and row.fee_type == "税费":
            decision = _update_decision(
                row,
                status=PriceAuditRowDecision.Status.COMPLETED,
                result_type=PriceAuditRowDecision.ResultType.SKIPPED,
                reviewed_amount=row.submitted_amount,
                reduction_amount=ZERO,
                reason="税费当前版本不做智能审核，暂按送审金额保留。",
            )
            decision_map[row.id] = decision
            continue

        if row.row_type == PriceAuditSubmissionRow.RowType.GROUP:
            children = [item for item in rows if item.parent_sequence_no == row.sequence_no]
            child_decisions = [decision_map.get(item.id) for item in children]
            if _has_failed_dependency(child_decisions):
                decision = _update_decision(
                    row,
                    status=PriceAuditRowDecision.Status.FAILED,
                    result_type="",
                    error_message="父项存在未完成或失败的子项，无法汇总。",
                )
            else:
                reviewed_amount = _sum_amounts([item for item in child_decisions if item is not None])
                submitted_amount = row.submitted_amount or ZERO
                decision = _update_decision(
                    row,
                    status=PriceAuditRowDecision.Status.COMPLETED,
                    result_type=PriceAuditRowDecision.ResultType.AGGREGATED,
                    reviewed_amount=reviewed_amount,
                    reduction_amount=submitted_amount - reviewed_amount,
                    reason="由子项审核结果自动汇总生成。",
                )
            decision_map[row.id] = decision
            continue

        if row.row_type == PriceAuditSubmissionRow.RowType.SUMMARY and row.fee_type == "小计":
            top_level_rows = [
                item
                for item in rows
                if not item.parent_sequence_no
                and item.row_type in (
                    PriceAuditSubmissionRow.RowType.LEAF,
                    PriceAuditSubmissionRow.RowType.GROUP,
                )
                and item.fee_type not in SUMMARY_FEE_TYPES
            ]
            top_level_decisions = [decision_map.get(item.id) for item in top_level_rows]
            if _has_failed_dependency(top_level_decisions):
                decision = _update_decision(
                    row,
                    status=PriceAuditRowDecision.Status.FAILED,
                    result_type="",
                    error_message="存在未完成或失败的顶层费用项，无法计算小计。",
                )
            else:
                reviewed_amount = _sum_amounts([item for item in top_level_decisions if item is not None])
                submitted_amount = row.submitted_amount or ZERO
                decision = _update_decision(
                    row,
                    status=PriceAuditRowDecision.Status.COMPLETED,
                    result_type=PriceAuditRowDecision.ResultType.AGGREGATED,
                    reviewed_amount=reviewed_amount,
                    reduction_amount=submitted_amount - reviewed_amount,
                    reason="由顶层费用项自动汇总生成。",
                )
            decision_map[row.id] = decision
            continue

        if row.row_type == PriceAuditSubmissionRow.RowType.SUMMARY and row.fee_type == "合计":
            subtotal_row = next((item for item in rows if item.fee_type == "小计"), None)
            tax_row = next((item for item in rows if item.fee_type == "税费"), None)
            subtotal_decision = decision_map.get(subtotal_row.id) if subtotal_row else None
            tax_decision = decision_map.get(tax_row.id) if tax_row else None
            if _has_failed_dependency([subtotal_decision, tax_decision]):
                decision = _update_decision(
                    row,
                    status=PriceAuditRowDecision.Status.FAILED,
                    result_type="",
                    error_message="小计或税费结果不可用，无法计算合计。",
                )
            else:
                reviewed_amount = (
                    (subtotal_decision.reviewed_amount if subtotal_decision else ZERO)
                    or ZERO
                ) + ((tax_decision.reviewed_amount if tax_decision else ZERO) or ZERO)
                submitted_amount = row.submitted_amount or ZERO
                decision = _update_decision(
                    row,
                    status=PriceAuditRowDecision.Status.COMPLETED,
                    result_type=PriceAuditRowDecision.ResultType.AGGREGATED,
                    reviewed_amount=reviewed_amount,
                    reduction_amount=submitted_amount - reviewed_amount,
                    reason="由小计和税费自动汇总生成。",
                )
            decision_map[row.id] = decision


def _update_submission_totals(submission: PriceAuditSubmission) -> None:
    """更新送审单总金额。"""

    rows = list(submission.rows.all())
    total_row = next((row for row in rows if row.fee_type == "合计"), None)
    total_decision = getattr(total_row, "decision", None) if total_row else None
    submission.submitted_total_amount = total_row.submitted_amount if total_row else None
    submission.reviewed_total_amount = (
        total_decision.reviewed_amount
        if total_decision and total_decision.status == PriceAuditRowDecision.Status.COMPLETED
        else None
    )
    if (
        submission.submitted_total_amount is not None
        and submission.reviewed_total_amount is not None
    ):
        submission.reduction_total_amount = (
            submission.submitted_total_amount - submission.reviewed_total_amount
        )
    else:
        submission.reduction_total_amount = None


@shared_task(bind=True)
def process_price_audit_submission(self, submission_id: int) -> None:
    """异步处理一份价格送审单。"""

    submission = PriceAuditSubmission.objects.select_related("price_batch").get(id=submission_id)
    _update_submission_progress(
        submission,
        status=PriceAuditSubmission.Status.PROCESSING,
        current_step=PriceAuditSubmission.Step.PARSING,
        progress_percent=5,
        total_rows=0,
        processed_rows=0,
        failed_rows=0,
        current_message="正在解析送审表。",
        error_message="",
        report_json={},
    )

    try:
        submission.rows.all().delete()
        populate_submission_rows(submission)

        leaf_rows = submission.rows.filter(
            row_type=PriceAuditSubmissionRow.RowType.LEAF
        ).order_by("excel_row_no")
        total_rows = leaf_rows.count()
        _update_submission_progress(
            submission,
            current_step=PriceAuditSubmission.Step.REVIEWING,
            progress_percent=10 if total_rows else 80,
            total_rows=total_rows,
            processed_rows=0,
            failed_rows=0,
            current_message=(
                f"已解析送审表，待审核 {total_rows} 条明细。"
                if total_rows
                else "送审表中没有需要逐条审核的明细，开始汇总。"
            ),
        )

        failed_leaf_count = 0
        # 明细行循环由程序控制；AI 只负责审核当前这一行。
        for index, row in enumerate(leaf_rows, start=1):
            decision = review_leaf_row(row)
            if decision.status == PriceAuditRowDecision.Status.FAILED:
                failed_leaf_count += 1
            _update_submission_progress(
                submission,
                current_step=PriceAuditSubmission.Step.REVIEWING,
                progress_percent=10 + int(index / total_rows * 70) if total_rows else 80,
                processed_rows=index,
                failed_rows=failed_leaf_count,
                current_message=f"正在审核第 {index}/{total_rows} 条明细：{row.fee_type}",
            )

        _update_submission_progress(
            submission,
            current_step=PriceAuditSubmission.Step.AGGREGATING,
            progress_percent=85,
            current_message="正在汇总父项、小计和合计。",
        )
        _aggregate_non_leaf_rows(submission)

        failed_count = PriceAuditRowDecision.objects.filter(
            submission_row__submission=submission,
            status=PriceAuditRowDecision.Status.FAILED,
        ).count()
        submission = PriceAuditSubmission.objects.prefetch_related("rows__decision").get(
            id=submission.id
        )
        _update_submission_totals(submission)
        submission.report_json = build_submission_report(submission)

        if failed_count == 0:
            _update_submission_progress(
                submission,
                current_step=PriceAuditSubmission.Step.EXPORTING,
                progress_percent=95,
                failed_rows=failed_count,
                current_message="正在生成审核表。",
            )
            content = build_audited_excel_content(submission)
            filename = f"{submission.project_name or 'price_audit'}_audited.xlsx"
            submission.audited_excel_file.save(
                filename,
                ContentFile(content),
                save=False,
            )

        submission.status = (
            PriceAuditSubmission.Status.FAILED
            if failed_count > 0
            else PriceAuditSubmission.Status.COMPLETED
        )
        submission.current_step = (
            PriceAuditSubmission.Step.FAILED
            if failed_count > 0
            else PriceAuditSubmission.Step.COMPLETED
        )
        submission.progress_percent = 100
        submission.failed_rows = failed_count
        submission.current_message = (
            f"审核完成，共 {failed_count} 行失败。"
            if failed_count > 0
            else "审核完成，审核表已生成。"
        )
        submission.error_message = (
            f"共 {failed_count} 行审核失败。"
            if failed_count > 0
            else ""
        )
        submission.save(
            update_fields=[
                "submitted_total_amount",
                "reviewed_total_amount",
                "reduction_total_amount",
                "status",
                "current_step",
                "progress_percent",
                "failed_rows",
                "current_message",
                "error_message",
                "report_json",
                "audited_excel_file",
                "updated_at",
            ]
        )
    except Exception as exc:  # pragma: no cover - 依赖运行时与外部服务
        logger.exception("价格送审单 %s 审核失败: %s", submission_id, exc)
        _update_submission_progress(
            submission,
            status=PriceAuditSubmission.Status.FAILED,
            current_step=PriceAuditSubmission.Step.FAILED,
            progress_percent=100,
            current_message="审核失败。",
            error_message=str(exc),
            report_json={
                "submission_id": submission.id,
                "status": PriceAuditSubmission.Status.FAILED,
                "error": str(exc),
            },
        )
