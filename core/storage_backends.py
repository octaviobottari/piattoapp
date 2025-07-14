from storages.backends.s3boto3 import S3Boto3Storage
from django.conf import settings

class MediaStorage(S3Boto3Storage):
    location = 'media'
    file_overwrite = False
    default_acl = 'public-read'
    
    def get_available_name(self, name, max_length=None):
        # Esto asegura que se creen las carpetas necesarias
        dirname = os.path.dirname(name)
        if dirname:
            # Simplemente intentar acceder a la "carpeta" es suficiente para que exista en S3
            self.bucket.Object(dirname + '/').put()
        return super().get_available_name(name, max_length)
