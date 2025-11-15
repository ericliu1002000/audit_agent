import pymysql

pymysql.install_as_MySQLdb()

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover
    pass

from .celery import app as celery_app

__all__ = ("celery_app",)
