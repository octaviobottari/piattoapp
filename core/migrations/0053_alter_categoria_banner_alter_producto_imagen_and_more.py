import core.models
import core.storage_backends
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0052_alter_restaurante_logo'),
    ]

    operations = [
        migrations.AlterField(
            model_name='categoria',
            name='banner',
            field=models.ImageField(blank=True, null=True, storage=core.storage_backends.MediaStorage(), upload_to=core.models.get_restaurante_media_path),
        ),
        migrations.AlterField(
            model_name='producto',
            name='imagen',
            field=models.ImageField(blank=True, null=True, storage=core.storage_backends.MediaStorage(), upload_to=core.models.get_restaurante_media_path),
        ),
        migrations.AlterField(
            model_name='restaurantqr',
            name='qr_image',
            field=models.ImageField(blank=True, help_text='Imagen del QR generada', null=True, storage=core.storage_backends.MediaStorage(), upload_to=core.models.get_qr_upload_path),
        ),
    ]
