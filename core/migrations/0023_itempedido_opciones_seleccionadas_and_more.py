# Generated by Django 5.0.6 on 2025-04-22 15:28

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0022_remove_pedido_email'),
    ]

    operations = [
        migrations.AddField(
            model_name='itempedido',
            name='opciones_seleccionadas',
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name='producto',
            name='costo_produccion',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True, verbose_name='Costo de producción'),
        ),
        migrations.AddField(
            model_name='producto',
            name='es_nuevo',
            field=models.BooleanField(default=False, verbose_name='¿Es nuevo?'),
        ),
        migrations.AddField(
            model_name='producto',
            name='fecha_marcado_nuevo',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.CreateModel(
            name='OpcionProducto',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nombre', models.CharField(max_length=100)),
                ('descripcion', models.TextField(blank=True)),
                ('precio_adicional', models.DecimalField(decimal_places=2, default=0.0, max_digits=10)),
                ('producto', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='opciones', to='core.producto')),
            ],
            options={
                'ordering': ['id'],
            },
        ),
    ]
