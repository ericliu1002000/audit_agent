"""价格审核专用工具集。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from price_audit.models import GovernmentPriceItem, PriceAuditSubmissionRow
from price_audit.services.normalization import normalize_text
from price_audit.vector_store import get_price_audit_milvus_manager
from utils.vector_api import call_embedding_api


@dataclass
class PriceAuditToolCollector:
    """记录工具调用过程中命中的候选证据。"""

    candidates: list[dict[str, Any]] = field(default_factory=list)

    def add_candidates(self, items: list[dict[str, Any]]) -> None:
        seen_ids = {item.get("item_id") for item in self.candidates}
        for item in items:
            if item.get("item_id") in seen_ids:
                continue
            self.candidates.append(item)
            seen_ids.add(item.get("item_id"))


class PriceAuditToolset:
    """面向单条送审行的工具实例。"""

    def __init__(self, submission_row: PriceAuditSubmissionRow):
        self.submission_row = submission_row
        self.submission = submission_row.submission
        self.collector = PriceAuditToolCollector()

    def get_submission_row_context(self) -> dict[str, Any]:
        """返回当前行和父级行上下文。"""

        parent_row = None
        if self.submission_row.parent_sequence_no:
            parent_row = self.submission.rows.filter(
                sequence_no=self.submission_row.parent_sequence_no
            ).first()

        return {
            "submission_id": self.submission.id,
            "price_batch_id": self.submission.price_batch_id,
            "project_name": self.submission.project_name,
            "exhibition_center": {
                "id": self.submission.exhibition_center_id,
                "name": self.submission.get_exhibition_center_id_display(),
            },
            "project_nature": {
                "id": self.submission.project_nature,
                "name": self.submission.get_project_nature_display(),
            },
            "row": {
                "row_id": self.submission_row.id,
                "sequence_no": self.submission_row.sequence_no,
                "fee_type": self.submission_row.fee_type,
                "submitted_unit": self.submission_row.submitted_unit,
                "submitted_unit_price": (
                    str(self.submission_row.submitted_unit_price)
                    if self.submission_row.submitted_unit_price is not None
                    else None
                ),
                "submitted_quantity": (
                    str(self.submission_row.submitted_quantity)
                    if self.submission_row.submitted_quantity is not None
                    else None
                ),
                "submitted_days": (
                    str(self.submission_row.submitted_days)
                    if self.submission_row.submitted_days is not None
                    else None
                ),
                "submitted_amount": (
                    str(self.submission_row.submitted_amount)
                    if self.submission_row.submitted_amount is not None
                    else None
                ),
                "budget_note": self.submission_row.budget_note,
            },
            "parent_row": {
                "sequence_no": parent_row.sequence_no if parent_row else None,
                "fee_type": parent_row.fee_type if parent_row else None,
                "submitted_amount": (
                    str(parent_row.submitted_amount) if parent_row and parent_row.submitted_amount else None
                ),
                "budget_note": parent_row.budget_note if parent_row else None,
            },
        }

    def search_standard_price_candidates(
        self,
        query: str = "",
        unit: str = "",
        top_k: int = 5,
    ) -> dict[str, Any]:
        """查询标准价候选。"""

        query_text = normalize_text(query) or self.submission_row.fee_type
        unit_text = normalize_text(unit) or self.submission_row.submitted_unit
        embedding_input = " | ".join(filter(None, [query_text, unit_text]))
        vector = call_embedding_api(embedding_input)
        manager = get_price_audit_milvus_manager()
        hits = manager.search_candidates(
            vector,
            batch_id=self.submission.price_batch_id,
            top_k=top_k,
        )
        item_map = {
            item.id: item
            for item in GovernmentPriceItem.objects.filter(
                id__in=[hit["item_id"] for hit in hits]
            )
        }
        results: list[dict[str, Any]] = []
        normalized_unit = unit_text.replace("平米", "㎡")
        for hit in hits:
            item = item_map.get(hit["item_id"])
            if item is None:
                continue
            result = {
                "item_id": item.id,
                "material_name": item.material_name_raw,
                "spec_model": item.spec_model_raw,
                "unit": item.unit_raw,
                "benchmark_price": str(item.benchmark_price),
                "price_min": str(item.price_min) if item.price_min is not None else None,
                "price_max": str(item.price_max) if item.price_max is not None else None,
                "description": item.description,
                "score": hit["score"],
            }
            results.append(result)

        if normalized_unit:
            results.sort(
                key=lambda item: (
                    0 if normalize_text(item["unit"]).replace("平米", "㎡") == normalized_unit else 1,
                    -float(item["score"]),
                )
            )

        self.collector.add_candidates(results)
        return {"query": query_text, "unit": unit_text, "items": results}
