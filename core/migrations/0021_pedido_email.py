# Generated by Django 5.0.6 on 2025-04-16 01:37

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0020_pedido_codigo_descuento_pedido_costo_envio_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='pedido',
            name='email',
            field=models.EmailField(blank=True, default='no-email@example.com', max_length=254),
        ),
    ]
