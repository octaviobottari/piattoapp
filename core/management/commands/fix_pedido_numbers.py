# clickandeat/clickandeat/fix_pedidos.py
from core.models import Pedido, Restaurante

def fix_pedido_numbers():
    restaurantes = Restaurante.objects.all()
    for restaurante in restaurantes:
        pedidos = Pedido.objects.filter(restaurante=restaurante).order_by('fecha')
        for index, pedido in enumerate(pedidos, start=1):
            if pedido.numero_pedido is None or pedido.numero_pedido != index:
                pedido.numero_pedido = index
                pedido.save()
                print(f'Actualizado pedido #{pedido.id} del restaurante {restaurante.nombre_local} con numero_pedido={index}')
    print('Corrección de numero_pedido completada.')