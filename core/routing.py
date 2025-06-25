# core/routing.py
from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/pedidos/(?P<restaurante_id>\d+)/$', consumers.PedidosConsumer.as_asgi()),
]

