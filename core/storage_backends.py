# core/storage_backends.py
from django.conf import settings  # Add this import
from storages.backends.s3boto3 import S3Boto3Storage
import logging

logger = logging.getLogger(__name__)

logger.info(f"Usando almacenamiento: {settings.DEFAULT_FILE_STORAGE}")

class MediaStorage(S3Boto3Storage):
    location = 'media'
    file_overwrite = False
    default_acl = 'public-read'
