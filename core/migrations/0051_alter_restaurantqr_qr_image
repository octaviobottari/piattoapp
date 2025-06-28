import core.models
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0050_restaurantqr'),
    ]

    operations = [
        migrations.AlterField(
            model_name='restaurantqr',
            name='qr_image',
            field=models.ImageField(blank=True, help_text='Imagen del QR generada', null=True, upload_to=core.models.get_qr_upload_path),
        ),
    ]
