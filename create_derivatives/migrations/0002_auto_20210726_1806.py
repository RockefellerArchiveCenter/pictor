# Generated by Django 3.2.5 on 2021-07-26 18:06

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('create_derivatives', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='bag',
            name='as_data',
            field=models.JSONField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='bag',
            name='dimes_identifier',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
    ]
