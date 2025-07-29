from django.db import migrations, models
import django.utils.timezone

class Migration(migrations.Migration):
    dependencies = [
        ('core', '0053_alter_categoria_banner_alter_producto_imagen_and_more'),  # Adjust based on your previous migration
    ]

    operations = [
        migrations.AddField(
            model_name='Pedido',
            name='fecha_procesando_pago',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='Pedido',
            name='error_pago_mensaje',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='Pedido',
            name='estado',
            field=models.CharField(
                choices=[
                    ('procesando_pago', 'Procesando Pago'),
                    ('pendiente', 'Pendiente'),
                    ('pagado', 'Pagado'),
                    ('en_preparacion', 'En preparación'),
                    ('listo', 'Listo para entregar'),
                    ('entregado', 'Entregado'),
                    ('cancelado', 'Cancelado'),
                    ('archivado', 'Archivado'),
                    ('en_entrega', 'En entrega'),
                    ('error_pago', 'Error en Pago'),
                ],
                default='pendiente',
                max_length=20,
            ),
        ),
    ]