# Generated by Django 5.2.1 on 2025-06-08 11:21

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='userprofile',
            name='open_date',
            field=models.DateField(blank=True, null=True, verbose_name='개업일자'),
        ),
        migrations.AddField(
            model_name='userprofile',
            name='representative_name',
            field=models.CharField(blank=True, max_length=50, null=True, verbose_name='대표자명'),
        ),
    ]
