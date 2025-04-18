# Generated by Django 4.2.7 on 2025-04-14 03:07

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('portfolio', '0002_stock_day_change_stock_day_change_percentage_and_more'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='stock',
            name='current_price',
        ),
        migrations.RemoveField(
            model_name='stock',
            name='day_change',
        ),
        migrations.RemoveField(
            model_name='stock',
            name='day_change_percentage',
        ),
        migrations.RemoveField(
            model_name='stock',
            name='dividend_yield',
        ),
        migrations.RemoveField(
            model_name='stock',
            name='fifty_two_week_high',
        ),
        migrations.RemoveField(
            model_name='stock',
            name='fifty_two_week_low',
        ),
        migrations.RemoveField(
            model_name='stock',
            name='last_updated',
        ),
        migrations.RemoveField(
            model_name='stock',
            name='pe_ratio',
        ),
        migrations.RemoveField(
            model_name='stock',
            name='previous_close',
        ),
    ]
