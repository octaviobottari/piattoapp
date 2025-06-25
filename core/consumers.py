import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from core.models import Restaurante, Pedido
from redis.asyncio import ConnectionError as RedisConnectionError

logger = logging.getLogger(__name__)

class PedidosConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user = self.scope["user"]
        if not self.user.is_authenticated or not isinstance(self.user, Restaurante):
            logger.warning("Conexión WebSocket rechazada: usuario no autenticado o no es restaurante")
            await self.close()
            return

        self.restaurante_id = str(self.user.id)
        self.group_name = f'pedidos_restaurante_{self.restaurante_id}'
        try:
            await self.channel_layer.group_add(self.group_name, self.channel_name)
            await self.accept()
            logger.info(f"WebSocket conectado para restaurante {self.restaurante_id}")
        except RedisConnectionError as e:
            logger.error(f"Error al conectar a Redis: {e}")
            await self.send(text_data=json.dumps({
                'error': 'No se pudo conectar al servidor de notificaciones. Por favor, intenta de nuevo.'
            }))
            await self.close()

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            try:
                await self.channel_layer.group_discard(self.group_name, self.channel_name)
                logger.info(f"WebSocket desconectado para restaurante {self.restaurante_id}, código: {close_code}")
            except RedisConnectionError as e:
                logger.error(f"Error al desconectar de Redis: {e}")

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            logger.debug(f"Mensaje recibido: {data}")
            await self.send(text_data=json.dumps({
                'type': 'message_received',
                'message': 'Mensaje recibido, pero no procesado',
                'data': data
            }))
        except json.JSONDecodeError as e:
            logger.error(f"Error al parsear JSON: {e}")
            await self.send(text_data=json.dumps({
                'error': 'Formato JSON inválido'
            }))
        except RedisConnectionError as e:
            logger.error(f"Error en Redis al procesar mensaje: {e}")
            await self.send(text_data=json.dumps({
                'error': 'Error en el servidor de notificaciones'
            }))

    async def new_pedido(self, event):
        try:
            pedido = await database_sync_to_async(Pedido.objects.get)(id=event['pedido_id'])
            await self.send(text_data=json.dumps({
                'type': 'new_pedido',
                'pedido_id': event['pedido_id'],
                'numero_pedido': pedido.numero_pedido,
                'estado': pedido.estado,
                'message': event.get('message', '')
            }))
            logger.info(f"Notificación enviada para pedido {event['pedido_id']} al restaurante {self.restaurante_id}")
        except Pedido.DoesNotExist:
            logger.error(f"Pedido {event['pedido_id']} no encontrado")
            await self.send(text_data=json.dumps({
                'error': f'Pedido {event["pedido_id"]} no encontrado'
            }))
        except Exception as e:
            logger.error(f"Error al enviar notificación de nuevo pedido: {e}")
            await self.send(text_data=json.dumps({
                'error': 'Error al procesar el nuevo pedido'
            }))

    async def pedido_updated(self, event):
        try:
            pedido = await database_sync_to_async(Pedido.objects.get)(id=event['pedido_id'])
            await self.send(text_data=json.dumps({
                'type': 'pedido_updated',
                'pedido_id': event['pedido_id'],
                'numero_pedido': pedido.numero_pedido,
                'estado': pedido.estado,
                'tiempo_estimado': pedido.tiempo_estimado or None,
                'message': event.get('message', '')
            }))
            logger.info(f"Notificación de actualización enviada para pedido {event['pedido_id']} al restaurante {self.restaurante_id}")
        except Pedido.DoesNotExist:
            logger.error(f"Pedido {event['pedido_id']} no encontrado")
            await self.send(text_data=json.dumps({
                'error': f'Pedido {event["pedido_id"]} no encontrado'
            }))
        except Exception as e:
            logger.error(f"Error al enviar notificación de actualización: {e}")
            await self.send(text_data=json.dumps({
                'error': 'Error al procesar la actualización del pedido'
            }))