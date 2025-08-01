# Generated by Django 5.0.6 on 2025-05-09 12:31

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0035_alter_categoria_banner_alter_producto_imagen_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='restaurante',
            name='cash_discount_enabled',
            field=models.BooleanField(default=False, verbose_name='Habilitar descuento por pago en efectivo'),
        ),
        migrations.AddField(
            model_name='restaurante',
            name='cash_discount_percentage',
            field=models.PositiveIntegerField(default=0, validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(50)], verbose_name='Porcentaje de descuento por pago en efectivo'),
        ),
    ]
