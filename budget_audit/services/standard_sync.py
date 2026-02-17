from __future__ import annotations

from typing import Dict

from django.db import transaction

from budget_audit.models import BudgetPriceItem
from budget_audit.services.excel_parser import parse_standard_price_excel
from budget_audit.services.milvus import get_budget_milvus_manager
from utils.vector_api import call_siliconflow_qwen3_embedding_api


def import_standard_price_excel(
    uploaded_file,
    *,
    region: str,
    publish_month: str,
    replace_existing: bool = True,
    default_tax_included: bool = True,
    embedding_timeout: float = 60.0,
) -> Dict[str, int]:
    """导入标准价格表并同步到 Milvus。"""

    rows = parse_standard_price_excel(
        uploaded_file,
        region=region,
        publish_month=publish_month,
        default_tax_included=default_tax_included,
    )
    manager = get_budget_milvus_manager()

    deleted_count = 0
    if replace_existing:
        stale_ids = list(
            BudgetPriceItem.objects.filter(
                region=region, publish_month=publish_month
            ).values_list("id", flat=True)
        )
        deleted_count = len(stale_ids)
        if stale_ids:
            BudgetPriceItem.objects.filter(id__in=stale_ids).delete()
            manager.delete_items(stale_ids)

    created_items = []
    with transaction.atomic():
        for row in rows:
            item = BudgetPriceItem.objects.create(**row)
            created_items.append(item)

    indexed_count = 0
    index_failed_count = 0
    for item in created_items:
        try:
            vector = call_siliconflow_qwen3_embedding_api(
                item.embedding_text, timeout=embedding_timeout
            )
            manager.upsert_item(
                item_id=item.id,
                unit=item.unit or "",
                is_tax_included=item.is_tax_included,
                embedding_text=item.embedding_text,
                vector=vector,
            )
            indexed_count += 1
        except Exception:
            index_failed_count += 1

    return {
        "parsed": len(rows),
        "created": len(created_items),
        "deleted": deleted_count,
        "indexed": indexed_count,
        "index_failed": index_failed_count,
    }

