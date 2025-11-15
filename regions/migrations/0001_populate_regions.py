from django.db import migrations, models


def forward_func(apps, schema_editor):
    Province = apps.get_model('regions', 'Province')
    City = apps.get_model('regions', 'City')

    from regions.data import CITIES_DATA, PROVINCES_DATA

    provinces = [Province(code=item['code'], name=item['name']) for item in PROVINCES_DATA]
    Province.objects.bulk_create(provinces, ignore_conflicts=True)

    code_to_province = {province.code: province for province in Province.objects.all()}
    cities = []
    for city_item in CITIES_DATA:
        province = code_to_province.get(city_item['provinceCode'])
        if not province:
            continue
        cities.append(
            City(
                code=city_item['code'],
                name=city_item['name'],
                province=province,
            )
        )

    if cities:
        City.objects.bulk_create(cities, ignore_conflicts=True)


def reverse_func(apps, schema_editor):
    Province = apps.get_model('regions', 'Province')
    City = apps.get_model('regions', 'City')

    City.objects.all().delete()
    Province.objects.all().delete()


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name='Province',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('name', models.CharField(db_index=True, max_length=100, unique=True, verbose_name='省份名称')),
                (
                    'code',
                    models.CharField(
                        db_index=True,
                        help_text='例如：11',
                        max_length=20,
                        unique=True,
                        verbose_name='省份代码',
                    ),
                ),
            ],
            options={
                'verbose_name': '省份',
                'verbose_name_plural': '省份',
            },
        ),
        migrations.CreateModel(
            name='City',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('name', models.CharField(db_index=True, max_length=100, verbose_name='城市名称')),
                (
                    'code',
                    models.CharField(
                        db_index=True,
                        help_text='例如：1101',
                        max_length=20,
                        unique=True,
                        verbose_name='城市代码',
                    ),
                ),
                (
                    'province',
                    models.ForeignKey(
                        on_delete=models.CASCADE,
                        related_name='cities',
                        to='regions.province',
                        verbose_name='所属省份',
                    ),
                ),
            ],
            options={
                'verbose_name': '城市',
                'verbose_name_plural': '城市',
            },
        ),
        migrations.AlterUniqueTogether(
            name='city',
            unique_together={('province', 'name')},
        ),
        migrations.RunPython(forward_func, reverse_func),
    ]
