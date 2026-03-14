import os

from celery import Celery
from celery.signals import worker_ready
from django.core.management import call_command


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "audit_agent.settings")

app = Celery("audit_agent")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


@worker_ready.connect
def bootstrap_milvus_collections_on_worker_ready(**kwargs):
    call_command("ensure_vector_collections")
