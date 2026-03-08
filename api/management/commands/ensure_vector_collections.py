"""统一初始化项目内所有 Milvus collection。"""

from django.core.management.base import BaseCommand

from indicators.vector_utils import get_milvus_manager
from price_audit.vector_store import get_price_audit_milvus_manager


class Command(BaseCommand):
    help = "确保项目所需的 Milvus collection 与索引均已创建。"

    def handle(self, *args, **options):
        indicator_manager = get_milvus_manager()
        indicator_manager.ensure_collection()
        self.stdout.write(
            self.style.SUCCESS(
                f"Indicators collection ready: {indicator_manager.collection_name}"
            )
        )

        price_manager = get_price_audit_milvus_manager()
        price_manager.ensure_collection()
        self.stdout.write(
            self.style.SUCCESS(
                f"Price audit collection ready: {price_manager.collection_name}"
            )
        )
