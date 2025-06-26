import os
import django
from django.conf import settings

# Configurar el entorno lo primero
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'piatto.settings')
django.setup()  # Inicializa Django explícitamente

from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
import core.routing

print("Inicializando ASGI application...")
application = ProtocolTypeRouter({
    'http': get_asgi_application(),
    'websocket': AuthMiddlewareStack(
        URLRouter(
            core.routing.websocket_urlpatterns
        )
    ),
})
print("ASGI application inicializada. Intentando conectar a Redis...")
