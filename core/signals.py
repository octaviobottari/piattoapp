from django.db.models.signals import post_save
from django.dispatch import receiver
from core.models import Restaurante
from django.conf import settings
import os

@receiver(post_save, sender=Restaurante)
def crear_directorios_medios(sender, instance, created, **kwargs):
    if created:
        directorio_base = os.path.join(settings.MEDIA_ROOT, instance.username)
        subdirectorios = ['categorias_banners', 'logos', 'productos']
        for subdir in subdirectorios:
            directorio = os.path.join(directorio_base, subdir)
            os.makedirs(directorio, exist_ok=True)