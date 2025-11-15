from django.db import migrations, models
import django.db.models.deletion


def forwards(apps, schema_editor):
    Indicator = apps.get_model('indicators', 'Indicator')
    Province = apps.get_model('regions', 'Province')

    provinces = list(Province.objects.all())
    name_map = {p.name: p for p in provinces}
    code_map = {p.code: p for p in provinces}
    fallback = next((p for p in provinces if p.id == 2), provinces[0] if provinces else None)

    indicators = Indicator.objects.all().iterator()
    for indicator in indicators:
        raw_value = (getattr(indicator, 'province_text', '') or '').strip()
        province = name_map.get(raw_value) or code_map.get(raw_value) or fallback
        indicator.province_id = province
        indicator.save(update_fields=['province_id'])


def backwards(apps, schema_editor):
    Indicator = apps.get_model('indicators', 'Indicator')

    for indicator in Indicator.objects.select_related('province_id').iterator():
        province = indicator.province_id
        indicator.province_text = province.name if province else ''
        indicator.save(update_fields=['province_text'])


class Migration(migrations.Migration):

    dependencies = [
        ('regions', '0001_populate_regions'),
        ('indicators', '0002_remove_indicator_source_indicator_province_and_more'),
    ]

    operations = [
        migrations.RenameField(
            model_name='indicator',
            old_name='province',
            new_name='province_text',
        ),
        migrations.AddField(
            model_name='indicator',
            name='province_id',
            field=models.ForeignKey(
                blank=True,
                db_column='province_id',
                default=None,
                help_text='数据来源或发布主体，例如“天津市”“广东省”。',
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='indicators',
                to='regions.province',
                verbose_name='指标省份',
            ),
        ),
        migrations.RunPython(forwards, backwards),
        migrations.AlterField(
            model_name='indicator',
            name='province_id',
            field=models.ForeignKey(
                db_column='province_id',
                default=2,
                help_text='数据来源或发布主体，例如“天津市”“广东省”。',
                on_delete=django.db.models.deletion.PROTECT,
                related_name='indicators',
                to='regions.province',
                verbose_name='指标省份',
            ),
        ),
        migrations.RemoveField(
            model_name='indicator',
            name='province_text',
        ),
    ]
