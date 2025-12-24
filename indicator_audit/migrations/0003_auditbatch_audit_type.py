from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("indicator_audit", "0002_auditfile_created_by"),
    ]

    operations = [
        migrations.AddField(
            model_name="auditbatch",
            name="audit_type",
            field=models.CharField(
                choices=[("declaration", "目标申报"), ("self_eval", "自评自查")],
                db_index=True,
                default="declaration",
                help_text="区分绩效目标申报与绩效自评自查两类业务。",
                max_length=32,
                verbose_name="审核类型",
            ),
        ),
    ]
