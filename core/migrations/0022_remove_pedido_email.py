# Generated by Django 5.0.6 on 2025-04-16 01:47

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0021_pedido_email'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='pedido',
            name='email',
        ),
    ]
