# core/urls.py
from django.urls import path, re_path
from django.views.generic import RedirectView
from django.conf.urls import handler500
from . import views

handler404 = 'core.views.error_view'
handler500 = 'core.views.error_view'

urlpatterns = [
    # Home and Auth routes
    path('', views.home, name='home'),
    path('terminos-y-condiciones/', views.terms_view, name='terms'),
    path('registro/', RedirectView.as_view(url='/login/', permanent=True), name='registro'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    
    # Panel routes
    path('panel/', views.panel_view, name='panel'),
    path('panel/mi_menu/', views.mi_menu, name='mi_menu'),
    path('panel/agregar_producto/', views.agregar_producto, name='agregar_producto'),
    path('panel/agregar_categoria/', views.agregar_categoria, name='agregar_categoria'),
    path('mass_price_change/', views.mass_price_change, name='mass_price_change'),
    path('mass_delete_products/', views.mass_delete_products, name='mass_delete_products'),
    
    # Pedidos routes
    path('panel/pedidos/', views.lista_pedidos, name='lista_pedidos'),
    path('panel/pedidos/procesando_pagos/html/', views.pedidos_procesando_pagos_html, name='pedidos_procesando_pagos_html'),
    path('panel/pedidos/<int:pedido_id>/confirmar_pago/', views.confirmar_pago, name='confirmar_pago'),
    path('panel/pedidos/<int:pedido_id>/rechazar_pago/', views.rechazar_pago, name='rechazar_pago'),
    path('panel/pedidos/pendientes/html/', views.pedidos_pendientes_html, name='pedidos_pendientes_html'),
    path('panel/pedidos/en_preparacion/html/', views.pedidos_en_preparacion_html, name='pedidos_en_preparacion_html'),
    path('panel/pedidos/listos/html/', views.pedidos_listos_html, name='pedidos_listos_html'),
    path('panel/pedidos/cancelados/', views.pedidos_cancelados, name='pedidos_cancelados'),
    path('panel/pedidos/en_entrega/', views.pedidos_en_entrega, name='pedidos_en_entrega'),
    path('panel/pedidos/todos/', views.todos_pedidos, name='todos_pedidos'),
    path('pedidos/imprimir/<int:pedido_id>/', views.imprimir_ticket, name='imprimir_ticket'),
    
    # Pedidos actions
    path('panel/pedidos/<int:pedido_id>/aceptar/', views.aceptar_pedido, name='aceptar_pedido'),
    path('panel/pedidos/<int:pedido_id>/rechazar/', views.rechazar_pedido, name='rechazar_pedido'),
    path('panel/pedidos/<int:pedido_id>/actualizar_estado/', views.actualizar_estado, name='actualizar_estado'),
    path('panel/pedidos/<int:pedido_id>/marcar_en_entrega/', views.marcar_en_entrega, name='marcar_en_entrega'),
    path('panel/pedidos/<int:pedido_id>/archivar/', views.archivar_pedido, name='archivar_pedido'),
    path('panel/pedidos/<int:pedido_id>/eliminar/', views.eliminar_pedido, name='eliminar_pedido'),
    path('panel/pedidos/<int:pedido_id>/json/', views.pedido_json, name='pedido_json'),
    
    # ✅ NUEVAS URLs SSE
    path('api/pedidos-sse/<int:restaurante_id>/', views.pedidos_sse, name='pedidos_sse'),
    path('api/pedidos-polling/<int:restaurante_id>/', views.pedidos_polling, name='pedidos_polling'),

    
    # Configuración routes
    path('configuracion-horarios/', views.configuracion_horarios, name='configuracion_horarios'),
    path('toggle-cerrado-manualmente/', views.toggle_cerrado_manualmente, name='toggle_cerrado_manualmente'),
    path('guardar-horarios-dia/', views.guardar_horarios_dia, name='guardar_horarios_dia'),
    path('guardar-demora/', views.guardar_demora, name='guardar_demora'),
    path('panel/configuraciones/', views.configuraciones, name='configuraciones'),
    path('panel/configurar_restaurante/', views.configurar_restaurante, name='configurar_restaurante'),
    path('panel/agregar_codigo_descuento/', views.agregar_codigo_descuento, name='agregar_codigo_descuento'),
    path('panel/eliminar_codigo_descuento/', views.eliminar_codigo_descuento, name='eliminar_codigo_descuento'),    
    path('producto/<int:producto_id>/aplicar-descuento/', views.aplicar_descuento_producto, name='aplicar_descuento_producto'),
    path('actualizar-metodos-pago/', views.actualizar_metodos_pago, name='actualizar_metodos_pago'),
    path('update-cash-discount/', views.update_cash_discount, name='update_cash_discount'),
    
    # Mercado Pago routes
    path('panel/vincular_mercado_pago/', views.vincular_mercado_pago, name='vincular_mercado_pago'),
    path('panel/mercado_pago_callback/', views.mercado_pago_callback, name='mercado_pago_callback'),
    path('panel/desvincular_mercado_pago/', views.desvincular_mercado_pago, name='desvincular_mercado_pago'),
    
    # Public restaurant routes
    path('<str:nombre_restaurante>/', views.restaurante_publico, name='restaurante_publico'),
    path('restaurante/<str:username>/estado/', views.obtener_estado_restaurante, name='obtener_estado_restaurante'),
    path('<str:nombre_restaurante>/validar_codigo_descuento/', views.validar_codigo_descuento, name='validar_codigo_descuento'),
    path('<str:nombre_restaurante>/confirmacion/<uuid:token>/', views.confirmacion_pedido, name='confirmacion_pedido'),   
    
    # Product and category routes
    path('panel/producto/<int:producto_id>/eliminar/', views.eliminar_producto, name='eliminar_producto'),
    path('panel/producto/<int:producto_id>/editar/', views.editar_producto, name='editar_producto'),
    path('panel/producto/<int:producto_id>/clonar/', views.clonar_producto, name='clonar_producto'),
    path('panel/categoria/<int:categoria_id>/eliminar/', views.eliminar_categoria, name='eliminar_categoria'),
    path('panel/categoria/<int:categoria_id>/editar/', views.editar_categoria, name='editar_categoria'),
    path('panel/gestionar_opciones_producto/<int:producto_id>/', views.gestionar_opciones_producto, name='gestionar_opciones_producto'),

    # Webhook route
    path('hello', views.hello, name="hello")
]

# Redirect for accounts
urlpatterns += [
    re_path(r'^accounts/login/$', RedirectView.as_view(url='/login/', query_string=True)),
]