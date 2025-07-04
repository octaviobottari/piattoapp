# Generated by Django 5.0.6 on 2025-04-10 15:25

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0012_remove_restaurante_whatsapp_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='pedido',
            name='motivo_cancelacion',
            field=models.CharField(blank=True, choices=[('no_llegamos_zona', 'No llegamos hasta la zona indicada'), ('monto_minimo', 'No llega al monto mínimo'), ('datos_insuficientes', 'Datos del cliente insuficientes'), ('pago_incorrecto', 'Datos del medio de pago incorrectos'), ('cliente_cancelo', 'El cliente lo canceló'), ('falta_productos', 'Falta de productos del restaurante'), ('fuera_servicio', 'Restaurante fuera de servicio'), ('zona_cerrada', 'Zona de reparto cerrada')], max_length=50, null=True),
        ),
        migrations.AddField(
            model_name='pedido',
            name='tiempo_estimado',
            field=models.CharField(blank=True, choices=[('15-30', 'Entre 15 y 30 minutos'), ('30-40', 'Entre 30 y 40 minutos'), ('45-60', 'Entre 45 y 60 minutos'), ('60-90', 'Entre 60 y 90 minutos')], max_length=10, null=True),
        ),
    ]
