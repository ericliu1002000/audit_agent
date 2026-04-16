"""价格审核专用工具集。"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
import re
from typing import Any

from price_audit.constants import PROJECT_NATURE_PERMANENT
from price_audit.models import GovernmentPriceItem, PriceAuditSubmissionRow
from price_audit.services.normalization import (
    normalize_text,
    normalize_text_no_space,
)
from price_audit.vector_store import get_price_audit_milvus_manager
from utils.vector_api import call_embedding_api


RULE_DEFINITIONS = (
    {
        "category": "official_fee",
        "pricing_mode": "official",
        "keywords": (
            "场地租",
            "场租",
            "施工管理费",
            "管理费",
            "电箱",
            "吊点",
            "网络",
            "宽带",
            "电费",
            "上水",
            "给排水",
            "气源",
        ),
        "preferred_units": ("㎡", "项"),
        "duplicate_risk_keywords": (),
    },
    {
        "category": "fabrication",
        "pricing_mode": "fabrication",
        "keywords": ("包边", "收边", "踢脚线", "压边条", "收口条"),
        "preferred_units": ("m",),
        "duplicate_risk_keywords": (),
    },
    {
        "category": "fabrication",
        "pricing_mode": "fabrication",
        "keywords": ("喷绘", "写真", "画面", "KT板画面"),
        "preferred_units": ("㎡",),
        "duplicate_risk_keywords": ("工厂制作人工",),
    },
    {
        "category": "standardized_item",
        "pricing_mode": "rental",
        "keywords": ("简易接待台",),
        "preferred_units": ("个", "套", "天"),
        "duplicate_risk_keywords": (),
    },
    {
        "category": "fabrication",
        "pricing_mode": "fabrication",
        "keywords": ("接待台", "前台", "服务台"),
        "preferred_units": ("m", "套"),
        "duplicate_risk_keywords": (),
    },
    {
        "category": "fabrication",
        "pricing_mode": "fabrication",
        "keywords": (
            "地台",
            "板墙",
            "墙体",
            "展板",
            "背景板",
            "地毯",
            "展位围挡",
            "围挡",
            "画面墙",
        ),
        "preferred_units": ("㎡",),
        "duplicate_risk_keywords": ("工厂制作人工",),
    },
    {
        "category": "standardized_item",
        "pricing_mode": "rental",
        "keywords": (
            "桌椅",
            "桌椅套装",
            "展架",
            "展具",
            "展柜",
            "简易展架",
            "射灯",
            "灯具",
            "LED屏",
            "屏幕",
            "桁架",
            "型材",
            "花卉租赁",
        ),
        "preferred_units": ("个", "套", "天", "㎡"),
        "duplicate_risk_keywords": ("电费", "基础电源及布线"),
    },
    {
        "category": "service",
        "pricing_mode": "service",
        "keywords": (
            "工厂制作人工",
            "现场搭建",
            "拆除人工",
            "人工",
            "设计费",
            "视频拍摄",
            "视频制作",
            "场务",
            "引导员",
            "劳务费",
            "保险费",
        ),
        "preferred_units": ("人天", "项"),
        "duplicate_risk_keywords": ("喷绘", "画面", "运输费"),
    },
    {
        "category": "transport_travel",
        "pricing_mode": "service",
        "keywords": (
            "运输费",
            "交通费",
            "住宿费",
            "餐费",
            "车费",
            "高铁费",
            "运输",
            "本地运输费",
        ),
        "preferred_units": ("次", "人次", "间", "辆"),
        "duplicate_risk_keywords": ("打包搭建", "运输费"),
    },
)
ALL_RULE_KEYWORDS = tuple(
    sorted(
        {keyword for rule in RULE_DEFINITIONS for keyword in rule["keywords"]},
        key=len,
        reverse=True,
    )
)


def _dedupe_strings(values: list[str]) -> list[str]:
    """保持顺序去重。"""

    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = normalize_text(value)
        if not text or text in seen:
            continue
        result.append(text)
        seen.add(text)
    return result


def _canonicalize_unit(value: str) -> str:
    """把常见单位收敛到统一口径。"""

    text = normalize_text_no_space(value).lower()
    if not text:
        return ""
    if any(token in text for token in ("㎡", "平方米", "平米", "m2")):
        return "㎡"
    if any(token in text for token in ("延长米", "延米")):
        return "m"
    if text in {"m", "米"} or "米/" in text or "/米" in text:
        return "m"
    if any(token in text for token in ("人/天", "人天", "人·天", "工日", "人日")):
        return "人天"
    if any(token in text for token in ("次往返", "往返", "车次")) or text == "次":
        return "次"
    if "人次" in text:
        return "人次"
    if "套" in text:
        return "套"
    if "个" in text:
        return "个"
    if "项" in text:
        return "项"
    if "间" in text:
        return "间"
    if "辆" in text:
        return "辆"
    if "秒" in text:
        return "秒"
    if text == "天":
        return "天"
    return text


def _units_are_comparable(left: str, right: str) -> bool:
    """宽松判断两个单位是否可比。"""

    if not left or not right:
        return True

    left_canonical = _canonicalize_unit(left)
    right_canonical = _canonicalize_unit(right)
    if left_canonical == right_canonical:
        return True

    comparable_groups = (
        {"个", "套"},
        {"次", "辆"},
    )
    for group in comparable_groups:
        if {left_canonical, right_canonical}.issubset(group):
            return True

    left_normalized = normalize_text_no_space(left)
    right_normalized = normalize_text_no_space(right)
    return (
        left_canonical and left_canonical in right_normalized
    ) or (
        right_canonical and right_canonical in left_normalized
    )


@dataclass
class PriceAuditToolCollector:
    """记录工具调用过程中命中的候选证据。"""

    candidates: list[dict[str, Any]] = field(default_factory=list)
    valid_candidate_ids: set[int] = field(default_factory=set)
    local_search_has_valid_price: bool | None = None
    context_snapshot: dict[str, Any] = field(default_factory=dict)

    def add_candidates(
        self,
        items: list[dict[str, Any]],
        valid_item_ids: set[int] | None = None,
    ) -> None:
        seen_ids = {item.get("item_id") for item in self.candidates}
        valid_item_ids = valid_item_ids or set()
        for item in items:
            if item.get("item_id") in seen_ids:
                continue
            self.candidates.append(item)
            seen_ids.add(item.get("item_id"))
        self.valid_candidate_ids.update(valid_item_ids)
        previous_state = self.local_search_has_valid_price
        self.local_search_has_valid_price = bool(valid_item_ids) or bool(previous_state)

    def note_local_search_result(self, has_valid_price: bool) -> None:
        previous_state = self.local_search_has_valid_price
        self.local_search_has_valid_price = has_valid_price or bool(previous_state)


class PriceAuditToolset:
    """面向单条送审行的工具实例。"""

    def __init__(self, submission_row: PriceAuditSubmissionRow):
        self.submission_row = submission_row
        self.submission = submission_row.submission
        self.collector = PriceAuditToolCollector()
        self.rule_hints = self._build_rule_hints()
        self.collector.context_snapshot = {
            "fee_category": self.rule_hints["fee_category"],
            "preferred_pricing_mode": self.rule_hints["preferred_pricing_mode"],
            "preferred_units": self.rule_hints["preferred_units"],
            "duplicate_risk_keywords": self.rule_hints["duplicate_risk_keywords"],
        }

    def get_submission_row_context(self) -> dict[str, Any]:
        """返回当前行与整单压缩上下文。"""

        rows = list(self.submission.rows.order_by("excel_row_no"))
        parent_row = None
        if self.submission_row.parent_sequence_no:
            parent_row = next(
                (
                    row
                    for row in rows
                    if row.sequence_no == self.submission_row.parent_sequence_no
                ),
                None,
            )

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
            "row": self._build_row_summary(self.submission_row),
            "parent_row": self._build_parent_row_summary(parent_row),
            "submission_overview": self._build_submission_overview(rows),
            "current_group_context": self._build_current_group_context(rows, parent_row),
            "same_fee_type_context": self._build_same_fee_type_context(rows),
            "rule_hints": self.rule_hints,
        }

    def search_standard_price_candidates(
        self,
        query: str = "",
        unit: str = "",
        top_k: int = 5,
    ) -> dict[str, Any]:
        """查询标准价候选。"""

        result = self._search_standard_price_candidates_internal(
            query=query,
            unit=unit,
            top_k=top_k,
            collect=True,
        )
        return result

    def build_evidence_json(
        self,
        *,
        reviewed_unit_price: str | None,
        reviewed_amount: str | None,
        notes: list[str],
    ) -> dict[str, Any]:
        """把上下文快照与本地标准价证据统一收敛。"""

        pricing_basis = self._infer_pricing_basis(
            reviewed_unit_price=reviewed_unit_price,
            reviewed_amount=reviewed_amount,
        )
        return {
            "candidates": self.collector.candidates,
            "notes": notes,
            "context_snapshot": self.collector.context_snapshot,
            "price_sources": [],
            "pricing_basis": pricing_basis,
        }

    def _build_rule_hints(self) -> dict[str, Any]:
        """根据费用名称和说明给当前行打业务标签。"""

        normalized_fee_type = normalize_text_no_space(self.submission_row.fee_type)
        normalized_budget_note = normalize_text_no_space(self.submission_row.budget_note)

        matched_rule = self._match_rule_definition(normalized_fee_type)
        if matched_rule is None and normalized_budget_note:
            matched_rule = self._match_rule_definition(
                normalize_text_no_space(
                    f"{self.submission_row.fee_type} {self.submission_row.budget_note}"
                )
            )

        project_is_permanent = self.submission.project_nature == PROJECT_NATURE_PERMANENT
        if matched_rule is None:
            pricing_mode = "procurement" if project_is_permanent else "service"
            preferred_units = self._default_preferred_units()
            duplicate_risk_keywords = []
            fee_category = "general"
        else:
            pricing_mode = matched_rule["pricing_mode"]
            if pricing_mode == "rental" and project_is_permanent:
                pricing_mode = "procurement"
            preferred_units = list(matched_rule["preferred_units"])
            duplicate_risk_keywords = list(matched_rule["duplicate_risk_keywords"])
            fee_category = matched_rule["category"]

        temporary_hint = (
            "常设陈列优先按耐久采购、固定安装和长期使用口径审核。"
            if project_is_permanent
            else "临时展会优先按租赁、复用和模块化口径审核。"
        )

        return {
            "fee_category": fee_category,
            "preferred_pricing_mode": pricing_mode,
            "preferred_units": preferred_units,
            "duplicate_risk_keywords": duplicate_risk_keywords,
            "temporary_vs_permanent_hint": temporary_hint,
        }

    def _match_rule_definition(self, normalized_text: str) -> dict[str, Any] | None:
        """按规则顺序匹配业务标签。"""

        for rule in RULE_DEFINITIONS:
            if any(keyword in normalized_text for keyword in rule["keywords"]):
                return rule
        return None

    def _default_preferred_units(self) -> list[str]:
        """给未命中规则的费用一个保守单位偏好。"""

        submitted_unit = _canonicalize_unit(self.submission_row.submitted_unit)
        return [submitted_unit] if submitted_unit else ["项"]

    def _resolve_preferred_units(self, unit_text: str) -> list[str]:
        """合并规则单位与调用方传入单位。"""

        units = list(self.rule_hints["preferred_units"])
        normalized_unit = _canonicalize_unit(unit_text)
        if normalized_unit and normalized_unit not in units:
            units.insert(0, normalized_unit)
        submitted_unit = _canonicalize_unit(self.submission_row.submitted_unit)
        if submitted_unit and submitted_unit not in units:
            units.append(submitted_unit)
        return _dedupe_strings(units)

    def _build_row_summary(self, row: PriceAuditSubmissionRow) -> dict[str, Any]:
        """压缩一行送审信息。"""

        return {
            "row_id": row.id,
            "sequence_no": row.sequence_no,
            "parent_sequence_no": row.parent_sequence_no,
            "fee_type": row.fee_type,
            "submitted_unit": row.submitted_unit,
            "submitted_unit_price": (
                str(row.submitted_unit_price) if row.submitted_unit_price is not None else None
            ),
            "submitted_quantity": (
                str(row.submitted_quantity) if row.submitted_quantity is not None else None
            ),
            "submitted_days": str(row.submitted_days) if row.submitted_days is not None else None,
            "submitted_amount": (
                str(row.submitted_amount) if row.submitted_amount is not None else None
            ),
            "budget_note": row.budget_note,
        }

    def _build_parent_row_summary(self, parent_row: PriceAuditSubmissionRow | None) -> dict[str, Any]:
        """兼容旧调用方返回的父项结构。"""

        if parent_row is None:
            return {
                "sequence_no": None,
                "fee_type": None,
                "submitted_amount": None,
                "budget_note": None,
            }
        return {
            "sequence_no": parent_row.sequence_no,
            "fee_type": parent_row.fee_type,
            "submitted_amount": (
                str(parent_row.submitted_amount) if parent_row.submitted_amount is not None else None
            ),
            "budget_note": parent_row.budget_note,
        }

    def _build_submission_overview(self, rows: list[PriceAuditSubmissionRow]) -> dict[str, Any]:
        """构造整单压缩摘要。"""

        leaf_rows = [row for row in rows if row.row_type == PriceAuditSubmissionRow.RowType.LEAF]
        top_level_rows = [row for row in leaf_rows if not row.parent_sequence_no]
        group_rows = [row for row in rows if row.row_type == PriceAuditSubmissionRow.RowType.GROUP]
        labels = [self._build_fee_label(row.fee_type) for row in leaf_rows]
        top_fee_types_summary = [
            {"label": label, "count": count}
            for label, count in Counter(labels).most_common(5)
        ]
        return {
            "project_name": self.submission.project_name,
            "exhibition_center_name": self.submission.get_exhibition_center_id_display(),
            "project_nature_name": self.submission.get_project_nature_display(),
            "leaf_row_count": len(leaf_rows),
            "group_row_count": len(group_rows),
            "top_level_rows": [self._build_fee_brief(row) for row in top_level_rows[:5]],
            "top_fee_types_summary": top_fee_types_summary,
        }

    def _build_current_group_context(
        self,
        rows: list[PriceAuditSubmissionRow],
        parent_row: PriceAuditSubmissionRow | None,
    ) -> dict[str, Any]:
        """返回当前父项和同组子项。"""

        if parent_row is None:
            return {
                "parent_row": None,
                "group_rows": [],
            }

        children = [
            self._build_fee_brief(row)
            for row in rows
            if row.parent_sequence_no == parent_row.sequence_no
        ]
        return {
            "parent_row": self._build_fee_brief(parent_row),
            "group_rows": children,
        }

    def _build_same_fee_type_context(self, rows: list[PriceAuditSubmissionRow]) -> list[dict[str, Any]]:
        """返回整单同类费用项的压缩视图。"""

        current_keywords = set(self._extract_fee_keywords(self.submission_row.fee_type))
        current_category = self.rule_hints["fee_category"]
        matched_rows: list[dict[str, Any]] = []
        for row in rows:
            if row.id == self.submission_row.id or row.row_type != PriceAuditSubmissionRow.RowType.LEAF:
                continue
            row_keywords = set(self._extract_fee_keywords(row.fee_type))
            row_category = self._build_fee_category_for_row(row)
            if current_keywords and current_keywords.intersection(row_keywords):
                matched_rows.append(self._build_fee_brief(row))
                continue
            if row_category == current_category and len(matched_rows) < 5:
                matched_rows.append(self._build_fee_brief(row))
        return matched_rows[:5]

    def _build_fee_brief(self, row: PriceAuditSubmissionRow) -> dict[str, Any]:
        """压缩展示费用项。"""

        return {
            "sequence_no": row.sequence_no,
            "fee_type": row.fee_type,
            "submitted_unit": row.submitted_unit,
            "submitted_quantity": (
                str(row.submitted_quantity) if row.submitted_quantity is not None else None
            ),
            "submitted_days": str(row.submitted_days) if row.submitted_days is not None else None,
            "submitted_amount": (
                str(row.submitted_amount) if row.submitted_amount is not None else None
            ),
        }

    def _build_fee_category_for_row(self, row: PriceAuditSubmissionRow) -> str:
        """单独给任意行推断费用类别。"""

        text = normalize_text_no_space(f"{row.fee_type} {row.budget_note}")
        for rule in RULE_DEFINITIONS:
            if any(keyword in text for keyword in rule["keywords"]):
                return rule["category"]
        return "general"

    def _build_fee_label(self, fee_type: str) -> str:
        """构造聚合展示用的费用标签。"""

        keywords = self._extract_fee_keywords(fee_type)
        if keywords:
            return keywords[0]
        return normalize_text(fee_type)

    def _extract_fee_keywords(self, fee_type: str) -> list[str]:
        """抽取费用核心关键词。"""

        normalized = normalize_text_no_space(fee_type)
        keywords = [keyword for keyword in ALL_RULE_KEYWORDS if keyword in normalized]
        stripped = re.sub(r"[（(].*?[)）]", "", normalized)
        parts = [part for part in re.split(r"[-—_/]", stripped) if part]
        if parts:
            keywords.append(parts[-1])
        if not keywords and normalized:
            keywords.append(normalized)
        return _dedupe_strings(keywords)

    def _candidate_has_effective_price(
        self,
        candidate: dict[str, Any],
        *,
        query_text: str,
        unit_text: str,
        preferred_units: list[str],
    ) -> bool:
        """判断标准价候选是否可直接作为本地有效价。"""

        if not candidate.get("benchmark_price"):
            return False

        candidate_unit = normalize_text(candidate.get("unit"))
        allowed_units = preferred_units or [unit_text]
        if allowed_units and not any(
            _units_are_comparable(candidate_unit, allowed_unit) for allowed_unit in allowed_units
        ):
            return False

        candidate_text = normalize_text_no_space(
            " ".join(
                filter(
                    None,
                    [
                        candidate.get("material_name"),
                        candidate.get("spec_model"),
                        candidate.get("description"),
                    ],
                )
            )
        )
        query_keywords = self._extract_fee_keywords(query_text)
        if query_keywords and not any(keyword in candidate_text for keyword in query_keywords):
            score = float(candidate.get("score") or 0)
            if score < 0.65:
                return False
        return True

    def _search_standard_price_candidates_internal(
        self,
        *,
        query: str,
        unit: str,
        top_k: int,
        collect: bool,
    ) -> dict[str, Any]:
        """本地标准价检索的内部实现。"""

        query_text = normalize_text(query) or self.submission_row.fee_type
        unit_text = normalize_text(unit) or self.submission_row.submitted_unit
        preferred_units = self._resolve_preferred_units(unit_text)
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
        valid_item_ids: set[int] = set()
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
            if self._candidate_has_effective_price(
                result,
                query_text=query_text,
                unit_text=unit_text,
                preferred_units=preferred_units,
            ):
                valid_item_ids.add(item.id)
            results.append(result)

        results.sort(
            key=lambda item: (
                0
                if any(
                    _units_are_comparable(item["unit"], preferred_unit)
                    for preferred_unit in preferred_units
                )
                else 1,
                -float(item["score"]),
            )
        )

        if collect:
            self.collector.add_candidates(results, valid_item_ids)
        else:
            self.collector.note_local_search_result(bool(valid_item_ids))

        return {
            "query": query_text,
            "unit": unit_text,
            "preferred_units": preferred_units,
            "has_valid_price": bool(valid_item_ids),
            "valid_item_ids": sorted(valid_item_ids),
            "items": results,
        }

    def _infer_pricing_basis(
        self,
        *,
        reviewed_unit_price: str | None,
        reviewed_amount: str | None,
    ) -> str:
        """推断当前审核使用的价格依据。"""

        if self.collector.valid_candidate_ids:
            return "local_standard"
        return "insufficient_evidence"
