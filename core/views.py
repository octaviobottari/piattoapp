import threading
from collections import defaultdict
import time
from django.shortcuts import render, redirect, get_object_or_404, get_list_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.db.models import Prefetch, F, Sum, Count
from django.views.decorators.http import require_POST, require_GET
from django.http import JsonResponse, HttpResponse, StreamingHttpResponse
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.forms.models import modelformset_factory  # Use modelformset_factory
from datetime import datetime, timedelta
from django.http import Http404
from django.urls import reverse
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import Table, TableStyle
from .forms import (
    RegistroRestauranteForm, LoginForm, ProductoForm, HorarioRestauranteFormSet,
    RestauranteDemoraForm, ConfigRestauranteForm, CodigoDescuentoForm, OpcionCategoriaForm, OpcionProductoForm,
    HOUR_CHOICES, MINUTE_CHOICES
)
from .models import Producto, Categoria, Pedido, ItemPedido, Restaurante, HorarioRestaurante, OpcionProducto, OpcionCategoria, RestaurantQR
from django.forms import formset_factory, inlineformset_factory
from django.views.decorators.csrf import csrf_protect, csrf_exempt
import json
from decimal import Decimal, InvalidOperation
import decimal
import logging
from itertools import groupby
from operator import attrgetter
from django.utils import timezone
from calendar import month_name
import qrcode
import base64
import hashlib
import os
from django.conf import settings
import io
from django.core.files import File
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage  # Importar default_storage
from botocore.exceptions import ClientError  # Importar ClientError
from rest_framework.decorators import api_view
from rest_framework.response import Response
import re
from django.views.decorators.cache import cache_page
from django.views.decorators.cache import never_cache
import requests
from django.core.cache import cache

logger = logging.getLogger(__name__)

def no_cache_view(view_func):
    def wrapper(request, *args, **kwargs):
        response = view_func(request, *args, **kwargs)
        response['Cache-Control'] = 'no-store, no-cache, must-revalidate, proxy-revalidate'
        response['Pragma'] = 'no-cache'
        response['Expires'] = '0'
        return response
    return wrapper

@never_cache
@no_cache_view
def error_view(request, exception=None):
    # Log del error
    logger.error(f"Error occurred for URL {request.path}: {str(exception)}", exc_info=True)

    # Determinar el mensaje y el código de estado según el tipo de error
    if isinstance(exception, Http404):
        error_message = "La página que buscas no existe."
        status = 404
    else:
        error_message = "Ha ocurrido un error inesperado. Por favor, contacta al soporte si el problema persiste."
        status = 500

    # Configurar el contexto para la plantilla error.html
    context = {
        'error': error_message,
        'restaurante': request.user if request.user.is_authenticated else None,
    }

    return render(request, 'core/error.html', context, status=status)

# Redirect registro to login
def registro_view(request):
    return redirect('login')

@never_cache
@no_cache_view
def terms_view(request):
    context = {
        'restaurantes': Restaurante.objects.filter(activo=True),
    }
    response = render(request, 'core/terminos-y-condiciones.html', context)
    response['Cache-Control'] = 'no-store, no-cache, must-revalidate, proxy-revalidate'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    return response

@never_cache
@no_cache_view
def login_view(request):
    # Redirect authenticated users to the panel
    if request.user.is_authenticated:
        return redirect('panel')

    if request.method == 'POST':
        form = LoginForm(data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            messages.success(request, f'Bienvenido de nuevo, {user.username}')
            next_url = request.GET.get('next', 'panel')
            return redirect(next_url)
        else:
            messages.error(request, 'Usuario o contraseña incorrectos')
    else:
        form = LoginForm()
    return render(request, 'core/login.html', {'form': form})

@login_required
@never_cache
@no_cache_view
def panel_view(request):
    restaurante = request.user
    now = timezone.localtime(timezone.now())
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    one_month_ago = now - timedelta(days=30)

    # Pedidos del último mes (archivados y listos)
    pedidos_mes = Pedido.objects.filter(
        restaurante=restaurante,
        fecha__gte=one_month_ago,
        estado__in=['listo', 'en_entrega', 'archivado']
    )

    # Ventas Hoy
    pedidos_hoy = pedidos_mes.filter(fecha__gte=start_of_day)
    ventas_hoy = pedidos_hoy.aggregate(total=Sum('total'))['total'] or Decimal('0.00')
    
    # Ventas Último Mes
    ventas_mes = pedidos_mes.aggregate(total=Sum('total'))['total'] or Decimal('0.00')

    # Calcular ganancias (estimación basada en costos de producción)
    ganancia_hoy = Decimal('0.00')
    ganancia_mes = Decimal('0.00')
    costos_mes = Decimal('0.00')
    
    for pedido in pedidos_mes:
        # Calcular costo de producción del pedido
        costo_pedido = Decimal('0.00')
        for item in pedido.items.all():
            if item.producto and item.producto.costo_produccion:
                costo_pedido += item.producto.costo_produccion * item.cantidad
            else:
                # Estimación conservadora del 60% del precio como costo si no hay costo definido
                costo_pedido += item.precio_unitario * Decimal('0.6') * item.cantidad
        
        if pedido.fecha >= start_of_day:
            ganancia_hoy += pedido.total - costo_pedido
        
        ganancia_mes += pedido.total - costo_pedido
        costos_mes += costo_pedido

    # Pedidos Pendientes
    pedidos_pendientes = Pedido.objects.filter(
        restaurante=restaurante,
        estado='pendiente'
    ).count()

    # Ticket promedio
    cantidad_pedidos_mes = pedidos_mes.count()
    ticket_promedio = ventas_mes / cantidad_pedidos_mes if cantidad_pedidos_mes > 0 else Decimal('0.00')

    # Margen de ganancia
    margen_ganancia = (ganancia_mes / ventas_mes * 100) if ventas_mes > 0 else Decimal('0.00')

    # Productos Más Vendidos con ganancias
    productos_populares_data = ItemPedido.objects.filter(
        pedido__restaurante=restaurante,
        pedido__fecha__gte=one_month_ago,
        pedido__estado__in=['listo', 'en_entrega', 'archivado']
    ).values('producto__nombre', 'producto__costo_produccion').annotate(
        cantidad_vendida=Sum('cantidad'),
        ventas_totales=Sum(F('cantidad') * F('precio_unitario'))
    ).order_by('-cantidad_vendida')[:10]

    productos_populares = []
    for item in productos_populares_data:
        costo_produccion = item['producto__costo_produccion'] or Decimal('0.00')
        ganancia_producto = item['ventas_totales'] - (costo_produccion * item['cantidad_vendida'])
        
        productos_populares.append({
            'nombre': item['producto__nombre'],
            'cantidad_vendida': item['cantidad_vendida'],
            'ventas_totales': item['ventas_totales'],
            'ganancia': ganancia_producto
        })

    # Métodos de pago más usados
    metodos_pago_data = pedidos_mes.values('metodo_pago').annotate(
        total=Sum('total'),
        cantidad=Count('id')
    ).order_by('-total')

    metodos_pago = []
    for metodo in metodos_pago_data:
        metodos_pago.append({
            'metodo': metodo['metodo_pago'],
            'total': metodo['total'],
            'cantidad': metodo['cantidad']
        })

    # Pedidos Urgentes o Retrasados (más de 40 minutos)
    forty_minutes_ago = now - timedelta(minutes=40)
    pedidos_retrasados = Pedido.objects.filter(
        restaurante=restaurante,
        estado__in=['pendiente', 'en_preparacion'],
        fecha__lte=forty_minutes_ago
    ).order_by('-fecha')[:5]

    # Pedidos con Error de Pago
    pedidos_error_pago = Pedido.objects.filter(
        restaurante=restaurante,
        estado='error_pago'
    ).order_by('-fecha')

    estadisticas = {
        'ventas_hoy': ventas_hoy,
        'ventas_mes': ventas_mes,
        'ganancia_hoy': ganancia_hoy,
        'ganancia_mes': ganancia_mes,
        'costos_mes': costos_mes,
        'margen_ganancia': margen_ganancia,
        'pedidos_pendientes': pedidos_pendientes,
        'ticket_promedio': ticket_promedio,
        'productos_populares': productos_populares,
        'metodos_pago': metodos_pago,
        'pedidos_retrasados': pedidos_retrasados,
        'pedidos_error_pago': pedidos_error_pago,
    }

    return render(request, 'core/panel.html', {
        'restaurante': restaurante,
        'estadisticas': estadisticas,
    })

def logout_view(request):
    logout(request)
    messages.info(request, 'Has cerrado sesión correctamente.')
    return redirect('home')


@login_required
def agregar_producto(request):
    if request.method == 'POST':
        form = ProductoForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            producto = form.save(commit=False)
            producto.restaurante = request.user
            nueva_categoria = form.cleaned_data.get('nueva_categoria')
            if nueva_categoria:
                categoria, created = Categoria.objects.get_or_create(
                    restaurante=request.user,
                    nombre=nueva_categoria
                )
                if created and form.cleaned_data.get('banner'):
                    categoria.banner = form.cleaned_data['banner']
                    categoria.save()
                producto.categoria = categoria
            try:
                producto.full_clean()  # Validate model fields
                producto.save()
                messages.success(request, 'Producto creado correctamente.')
                return redirect('mi_menu')
            except ValidationError as e:
                messages.error(request, f'Error al guardar el producto: {e}')
        else:
            messages.error(request, 'Error en el formulario. Verifica los datos.')
    else:
        form = ProductoForm(user=request.user)
    return render(request, 'core/mi_menu.html', {'form': form})


@login_required
@require_POST
@never_cache
@no_cache_view
def agregar_categoria(request):
    print("POST data:", request.POST)  # Debugging line to check incoming data
    print("FILES data:", request.FILES)  # Debugging line to check incoming files
    nombre = request.POST.get('nueva_categoria')
    banner = request.FILES.get('banner')

    if not nombre:
        messages.error(request, 'El nombre de la categoría es obligatorio.')
        return redirect('mi_menu')

    categoria = Categoria.objects.create(
        restaurante=request.user,
        nombre=nombre,
        banner=banner
    )
    messages.success(request, 'Categoría creada correctamente.')
    return redirect('mi_menu')

@login_required
@never_cache
@no_cache_view
def mi_menu(request):
    restaurante = request.user
    categorias = Categoria.objects.filter(restaurante=restaurante).prefetch_related('producto_set')
    productos_sin_categoria = Producto.objects.filter(categoria__isnull=True, restaurante=restaurante)
    context = {
        'restaurante': restaurante,
        'categorias': categorias,
        'productos_sin_categoria': productos_sin_categoria,
        'form': ProductoForm(user=restaurante),  # Pass the user to the form
        'percentage_range': range(51),

    }
    return render(request, 'core/mi_menu.html', context)

@login_required
@never_cache
@no_cache_view
def clonar_producto(request, producto_id):
    producto_original = get_object_or_404(Producto, id=producto_id, restaurante=request.user)
    logger.info(f"Cloning product: {producto_original.nombre}")
    logger.info(f"Original precio: {producto_original.precio}, precio_original: {producto_original.precio_original}, tiene_descuento: {producto_original.tiene_descuento}")
    logger.info(f"Original discount_percentage: {producto_original.discount_percentage}")
    logger.info(f"Option categories: {[oc.nombre for oc in producto_original.opcion_categorias.all()]}")

    nuevo_producto = Producto(
        restaurante=producto_original.restaurante,
        categoria=producto_original.categoria,
        nombre=f"{producto_original.nombre} (Copia)",
        descripcion=producto_original.descripcion,
        precio=producto_original.precio or Decimal('0.00'),
        precio_original=producto_original.precio_original if producto_original.precio_original is not None else None,
        costo_produccion=producto_original.costo_produccion if producto_original.costo_produccion is not None else None,
        stock=producto_original.stock,
        disponible=producto_original.disponible,
        agotado=producto_original.agotado,
        es_nuevo=producto_original.es_nuevo,
        imagen=producto_original.imagen,
        tiene_descuento=producto_original.tiene_descuento
    )
    try:
        nuevo_producto.full_clean()
        nuevo_producto.save()
    except ValidationError as e:
        logger.error(f"Validation error cloning product: {e}")
        messages.error(request, f'Error al clonar el producto: {e}')
        return redirect('mi_menu')

    for opcion_categoria_original in producto_original.opcion_categorias.all():
        nueva_opcion_categoria = OpcionCategoria(
            producto=nuevo_producto,
            nombre=opcion_categoria_original.nombre,
            max_selecciones=opcion_categoria_original.max_selecciones
        )
        nueva_opcion_categoria.save()
        for opcion in OpcionProducto.objects.filter(categoria=opcion_categoria_original):
            nueva_opcion = OpcionProducto(
                categoria=nueva_opcion_categoria,
                nombre=opcion.nombre,
                precio_adicional=opcion.precio_adicional or Decimal('0.00'),
                precio_adicional_original=opcion.precio_adicional_original if opcion.precio_adicional_original is not None else None,
                tiene_descuento=opcion.tiene_descuento
            )
            try:
                nueva_opcion.full_clean()
                nueva_opcion.save()
                logger.info(f"Cloned OpcionProducto: {nueva_opcion.nombre}, precio_adicional: {nueva_opcion.precio_adicional}, precio_adicional_original: {nueva_opcion.precio_adicional_original}, tiene_descuento: {nueva_opcion.tiene_descuento}")
            except ValidationError as e:
                logger.error(f"Validation error cloning OpcionProducto: {e}")

    logger.info(f"Cloned product: {nuevo_producto.nombre}")
    logger.info(f"Cloned precio: {nuevo_producto.precio}, precio_original: {nuevo_producto.precio_original}, tiene_descuento: {nuevo_producto.tiene_descuento}")
    messages.success(request, "Producto clonado correctamente.")
    return redirect('mi_menu')


@login_required
@never_cache
@no_cache_view
def gestionar_opciones_producto(request, producto_id):
    producto = get_object_or_404(Producto, id=producto_id, restaurante=request.user)
    restaurante = request.user  # El usuario autenticado es el restaurante

    CategoriaFormSet = modelformset_factory(
        OpcionCategoria,
        form=OpcionCategoriaForm,
        extra=1,
        can_delete=True
    )

    if request.method == 'POST':
        categoria_formset = CategoriaFormSet(request.POST, prefix='categoria', queryset=OpcionCategoria.objects.filter(producto=producto).order_by('id'))
        opcion_formsets = []

        if categoria_formset.is_valid():
            for categoria_form in categoria_formset:
                if categoria_form.cleaned_data and not categoria_form.cleaned_data.get('DELETE', False):
                    categoria_id = categoria_form.instance.id if categoria_form.instance.pk else None
                    if categoria_id:
                        OpcionFormSet = inlineformset_factory(
                            OpcionCategoria,
                            OpcionProducto,
                            form=OpcionProductoForm,
                            extra=0,
                            can_delete=True,
                            fields=['id', 'nombre', 'agotado', 'tiene_descuento', 'original_price']
                        )
                        formset = OpcionFormSet(
                            request.POST,
                            prefix=f'opcion-{categoria_id}',
                            instance=categoria_form.instance,
                            form_kwargs={'producto': producto}
                        )
                        opcion_formsets.append({'categoria_id': categoria_id, 'formset': formset})
        else:
            for categoria_form in categoria_formset:
                categoria_id = categoria_form.instance.id if categoria_form.instance.pk else None
                if categoria_id:
                    OpcionFormSet = inlineformset_factory(
                        OpcionCategoria,
                        OpcionProducto,
                        form=OpcionProductoForm,
                        extra=0,
                        can_delete=True,
                        fields=['id', 'nombre', 'agotado', 'tiene_descuento', 'original_price']
                    )
                    formset = OpcionFormSet(
                        request.POST,
                        prefix=f'opcion-{categoria_id}',
                        instance=categoria_form.instance,
                        form_kwargs={'producto': producto}
                    )
                    opcion_formsets.append({'categoria_id': categoria_id, 'formset': formset})

        if categoria_formset.is_valid():
            all_formsets_valid = True
            for fs in opcion_formsets:
                if not fs['formset'].is_valid():
                    all_formsets_valid = False
                    break

            if all_formsets_valid:
                with transaction.atomic():
                    for form in categoria_formset:
                        if form.cleaned_data and not form.cleaned_data.get('DELETE', False):
                            categoria = form.save(commit=False)
                            categoria.producto = producto
                            categoria.save()
                        elif form.cleaned_data.get('DELETE', False) and form.instance.pk:
                            form.instance.delete()

                    for fs in opcion_formsets:
                        for form in fs['formset']:
                            if form.cleaned_data and not form.cleaned_data.get('DELETE', False):
                                opcion = form.save(commit=False)
                                opcion.categoria_id = fs['categoria_id']
                                opcion.save()
                            elif form.cleaned_data.get('DELETE', False) and form.instance.pk:
                                form.instance.delete()

                    messages.success(request, 'Opciones guardadas correctamente.')
                    return redirect('gestionar_opciones_producto', producto_id=producto.id)
            else:
                messages.error(request, 'Errores en las opciones. Por favor, corrige los errores.')
        else:
            messages.error(request, 'Errores en las categorías. Por favor, corrige los errores.')
    else:
        categorias = OpcionCategoria.objects.filter(producto=producto).order_by('id')
        categoria_formset = CategoriaFormSet(
            queryset=categorias,
            prefix='categoria'
        )
        opcion_formsets = []

        for categoria in categorias:
            OpcionFormSet = inlineformset_factory(
                OpcionCategoria,
                OpcionProducto,
                form=OpcionProductoForm,
                extra=1,
                can_delete=True,
                fields=['id', 'nombre', 'agotado', 'tiene_descuento', 'original_price']
            )
            formset = OpcionFormSet(
                queryset=OpcionProducto.objects.filter(categoria=categoria).order_by('id'),
                prefix=f'opcion-{categoria.id}',
                instance=categoria,
                form_kwargs={'producto': producto}
            )
            opcion_formsets.append({'categoria_id': categoria.id, 'formset': formset})

    return render(request, 'core/gestionar_opciones.html', {  
        'producto': producto,
        'categoria_formset': categoria_formset,
        'opcion_formsets': opcion_formsets,
        'discount_percentage': producto.discount_percentage if producto.tiene_descuento else 0,
        'discount_factor': (100 - (producto.discount_percentage if producto.tiene_descuento else 0)) / 100,
        'restaurante': restaurante  # Agregado
    })

@login_required
@require_POST
@never_cache
@no_cache_view
def eliminar_producto(request, producto_id):
    producto = get_object_or_404(Producto, id=producto_id, restaurante=request.user)
    producto.delete()
    messages.success(request, 'Producto eliminado correctamente.')
    return redirect('mi_menu')

@require_POST
@login_required
@never_cache
@no_cache_view
def editar_producto(request, producto_id):
    producto = get_object_or_404(Producto, id=producto_id, restaurante=request.user)

    try:
        form = ProductoForm(request.POST, request.FILES, user=request.user, instance=producto)
        if form.is_valid():
            producto = form.save(commit=False)

            # Handle discount logic
            nuevo_precio = form.cleaned_data['precio']
            if producto.tiene_descuento and producto.discount_percentage > 0:
    # Si el producto tiene un descuento activo, actualizar precio_original y recalcular precio   
                producto.precio_original = nuevo_precio
                descuento_decimal = Decimal(str(producto.discount_percentage)) / Decimal('100')
                producto.precio = (producto.precio_original * (1 - descuento_decimal)).quantize(Decimal('0.01'))
            else:
    # Sin descuento, establecer precio directamente y limpiar precio_original
                producto.precio = nuevo_precio.quantize(Decimal('0.01'))
                producto.precio_original = None
                producto.tiene_descuento = False

            # Ensure validation before saving
            producto.full_clean()
            producto.save()

            # Return JSON response for AJAX
            return JsonResponse({
                'success': True,
                'nuevo_precio': str(producto.precio),
                'precio_original': str(producto.precio_original) if producto.precio_original else str(producto.precio),
                'tiene_descuento': producto.tiene_descuento,
                'discount_percentage': producto.discount_percentage,
                'ganancia_bruta': str(producto.ganancia_bruta) if producto.ganancia_bruta is not None else None,
                'ganancia_bruta_abs': str(producto.ganancia_bruta_abs) if producto.ganancia_bruta_abs is not None else None,
                'nombre': producto.nombre,
                'descripcion': producto.descripcion,
                'costo_produccion': str(producto.costo_produccion) if producto.costo_produccion is not None else None,
                'stock': producto.stock,
                'agotado': producto.agotado,
                'disponible': producto.disponible,
                'es_nuevo': producto.es_nuevo,
                'categoria_id': producto.categoria.id if producto.categoria else None,
                'categoria_nombre': producto.categoria.nombre if producto.categoria else None,
                'imagen_url': producto.imagen.url if producto.imagen else 'https://via.placeholder.com/170.png?text=Sin+Imagen',
            })
        else:
            logger.error("Form errors: %s", form.errors)
            return JsonResponse({'success': False, 'errors': form.errors}, status=400)
    except Exception as e:
        logger.exception("Error in editar_producto: %s", str(e))
        return JsonResponse({'success': False, 'error': f'Server error: {str(e)}'}, status=500)

@login_required
@require_POST
@never_cache
@no_cache_view
def eliminar_categoria(request, categoria_id):
    categoria = get_object_or_404(Categoria, id=categoria_id, restaurante=request.user)
    Producto.objects.filter(categoria=categoria).update(categoria=None)
    categoria.delete()
    messages.success(request, 'Categoría eliminada correctamente.')
    return redirect('mi_menu')

@login_required
@require_POST
@never_cache
@no_cache_view
def editar_categoria(request, categoria_id):
    categoria = get_object_or_404(Categoria, id=categoria_id, restaurante=request.user)
    nombre = request.POST.get('nombre')
    banner = request.FILES.get('banner')
    eliminar_banner = request.POST.get('eliminar_banner')

    if not nombre:
        messages.error(request, 'El nombre de la categoría es obligatorio.')
        return redirect('mi_menu')

    categoria.nombre = nombre
    if eliminar_banner and categoria.banner:
        categoria.banner.delete()
        categoria.banner = None
    if banner:
        if categoria.banner:
            categoria.banner.delete()
        categoria.banner = banner
    categoria.save()
    messages.success(request, 'Categoría actualizada correctamente.')
    return redirect('mi_menu')



@login_required
@require_POST
@never_cache
@no_cache_view
def mass_price_change(request):
    try:
        data = json.loads(request.body)
        logger.info(f"Mass price change request: {data}")
        product_ids = data.get('product_ids', [])
        discount_percentage = int(data.get('discount_percentage', 0))
        fixed_price = data.get('fixed_price', '')
        fixed_cost = data.get('fixed_cost', '')

        if not product_ids:
            logger.warning("No products selected for mass price change")
            return JsonResponse({'success': False, 'error': 'No se seleccionaron productos.'}, status=400)

        if discount_percentage < 0 or discount_percentage > 90:
            logger.warning(f"Invalid discount percentage: {discount_percentage}")
            return JsonResponse({'success': False, 'error': 'El porcentaje de descuento debe estar entre 0% y 90%.'}, status=400)

        fixed_price_decimal = None
        fixed_cost_decimal = None
        if fixed_price:
            try:
                fixed_price_decimal = Decimal(fixed_price.replace(',', '.')).quantize(Decimal('0.01'))
                if fixed_price_decimal < 0:
                    logger.warning(f"Negative fixed price: {fixed_price}")
                    return JsonResponse({'success': False, 'error': 'El precio fijo no puede ser negativo.'}, status=400)
            except (ValueError, InvalidOperation):
                logger.warning(f"Invalid fixed price: {fixed_price}")
                return JsonResponse({'success': False, 'error': 'Precio fijo inválido.'}, status=400)
        if fixed_cost:
            try:
                fixed_cost_decimal = Decimal(fixed_cost.replace(',', '.')).quantize(Decimal('0.01'))
                if fixed_cost_decimal < 0:
                    logger.warning(f"Negative fixed cost: {fixed_cost}")
                    return JsonResponse({'success': False, 'error': 'El costo fijo no puede ser negativo.'}, status=400)
            except (ValueError, InvalidOperation):
                logger.warning(f"Invalid fixed cost: {fixed_cost}")
                return JsonResponse({'success': False, 'error': 'Costo fijo inválido.'}, status=400)

        productos = Producto.objects.filter(id__in=product_ids, restaurante=request.user)
        if not productos.exists():
            logger.warning(f"No valid products found for IDs: {product_ids}")
            return JsonResponse({'success': False, 'error': 'No se encontraron productos válidos.'}, status=400)

        updated_products = []
        with transaction.atomic():
            for producto in productos:
                logger.info(f"Processing product ID {producto.id}: precio={producto.precio}, costo_produccion={producto.costo_produccion}, tiene_descuento={producto.tiene_descuento}")
                if discount_percentage > 0 and not producto.precio_original:
                    producto.precio_original = producto.precio

                if fixed_price_decimal is not None:
                    producto.precio = fixed_price_decimal
                    producto.precio_original = None
                    producto.tiene_descuento = False
                elif discount_percentage > 0:
                    original_price = producto.precio_original or producto.precio
                    descuento = original_price * (Decimal(discount_percentage) / Decimal(100))
                    producto.precio = (original_price - descuento).quantize(Decimal('0.01'))
                    producto.tiene_descuento = True
                elif discount_percentage == 0 and producto.tiene_descuento:
                    producto.precio = (producto.precio_original or producto.precio).quantize(Decimal('0.01'))
                    producto.precio_original = None
                    producto.tiene_descuento = False

                if fixed_cost_decimal is not None:
                    producto.costo_produccion = fixed_cost_decimal

                try:
                    producto.full_clean()
                    producto.save()
                except ValidationError as e:
                    logger.error(f"Validation error for product ID {producto.id}: {e}")
                    continue

                opciones_actualizadas = []
                for opcion_categoria in producto.opcion_categorias.all():
                    categoria_data = {
                        'nombre': opcion_categoria.nombre,
                        'max_selecciones': opcion_categoria.max_selecciones,
                        'opciones': []
                    }
                    for opcion in opcion_categoria.opciones.all():
                        if opcion.tiene_descuento:
                            opcion.aplicar_descuento(discount_percentage)
                            try:
                                opcion.full_clean()
                                opcion.save()
                            except ValidationError as e:
                                logger.error(f"Validation error for OpcionProducto ID {opcion.id}: {e}")
                                continue
                        categoria_data['opciones'].append({
                            'nombre': opcion.nombre,
                            'precio_adicional': str(opcion.precio_adicional),
                            'precio_adicional_original': str(opcion.precio_adicional_original) if opcion.precio_adicional_original else None,
                            'tiene_descuento': opcion.tiene_descuento,
                            'agotado': opcion.agotado
                        })
                    opciones_actualizadas.append(categoria_data)

                updated_products.append({
                    'id': producto.id,
                    'nuevo_precio': str(producto.precio),
                    'precio_original': str(producto.precio_original) if producto.precio_original else None,
                    'tiene_descuento': producto.tiene_descuento,
                    'discount_percentage': producto.discount_percentage,
                    'costo_produccion': str(producto.costo_produccion) if producto.costo_produccion is not None else None,
                    'ganancia_bruta': str(producto.ganancia_bruta) if producto.ganancia_bruta is not None else None,
                    'ganancia_bruta_abs': str(producto.ganancia_bruta_abs) if producto.ganancia_bruta_abs is not None else None,
                    'opciones_actualizadas': opciones_actualizadas
                })

        logger.info(f"Mass price change completed: {len(updated_products)} products updated")
        return JsonResponse({
            'success': True,
            'updated_products': updated_products
        })
    except (ValueError, TypeError, InvalidOperation) as e:
        logger.error(f"Invalid input in mass price change: {str(e)}")
        return JsonResponse({'success': False, 'error': f'Entrada inválida: {str(e)}'}, status=400)
    except Exception as e:
        logger.error(f"Unexpected error in mass price change: {str(e)}")
        return JsonResponse({'success': False, 'error': f'Error inesperado: {str(e)}'}, status=500)

@login_required
@require_POST
@never_cache
@no_cache_view
def mass_delete_products(request):
    try:
        data = json.loads(request.body)
        product_ids = data.get('product_ids', [])

        if not product_ids:
            return JsonResponse({'success': False, 'error': 'No se seleccionaron productos.'}, status=400)

        productos = Producto.objects.filter(id__in=product_ids, restaurante=request.user)
        if not productos.exists():
            return JsonResponse({'success': False, 'error': 'No se encontraron productos válidos.'}, status=400)

        with transaction.atomic():
            for producto in productos:
                producto.delete()

        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': f'Error al eliminar productos: {str(e)}'}, status=500)
    
class UltraFastPedidoCache:
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._data = defaultdict(dict)
                cls._instance._triggers = defaultdict(int)
                cls._instance._locks = defaultdict(threading.Lock)
            return cls._instance
    
    def set_pedidos(self, restaurante_id, pedidos):
        with self._locks[restaurante_id]:
            cache_key = f"pedidos_ultra_{restaurante_id}"
            self._data[restaurante_id] = {
                'pedidos': pedidos,
                'timestamp': timezone.now(),
                'version': self._data[restaurante_id].get('version', 0) + 1
            }
            # ✅ TRIGGER INMEDIATO
            self._triggers[restaurante_id] += 1
            # ✅ CACHE DE FALLBACK
            cache.set(cache_key, self._data[restaurante_id], 300)
    
    def get_pedidos(self, restaurante_id):
        with self._locks[restaurante_id]:
            # ✅ INTENTAR MEMORY PRIMERO
            if restaurante_id in self._data:
                return self._data[restaurante_id]
            
            # ✅ FALLBACK A CACHE DJANGO
            cache_key = f"pedidos_ultra_{restaurante_id}"
            cached = cache.get(cache_key)
            if cached:
                self._data[restaurante_id] = cached
                return cached
            
            return {'pedidos': [], 'version': 0, 'timestamp': timezone.now()}
    
    def check_trigger(self, restaurante_id, last_trigger):
        return self._triggers.get(restaurante_id, 0) > last_trigger

# INSTANCIA GLOBAL
ultra_cache = UltraFastPedidoCache()

class PedidoMemoryCache:
    _instance = None
    _cache = {}
    _lock = threading.Lock()
    _event_triggers = {}  # ✅ NUEVO: Trigger inmediato por restaurante
    
    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance
    
    def set_pedidos(self, restaurante_id, pedidos):
        with self._lock:
            cache_key = f"pedidos_activos_{restaurante_id}"
            self._cache[cache_key] = {
                'data': pedidos,
                'timestamp': timezone.now(),
                'version': self._cache.get(cache_key, {}).get('version', 0) + 1
            }
            # ✅ NUEVO: Trigger inmediato
            self._trigger_update(restaurante_id)
    
    def get_pedidos(self, restaurante_id):
        with self._lock:
            cache_key = f"pedidos_activos_{restaurante_id}"
            return self._cache.get(cache_key, {}).get('data', [])
    
    def get_version(self, restaurante_id):
        with self._lock:
            cache_key = f"pedidos_activos_{restaurante_id}"
            return self._cache.get(cache_key, {}).get('version', 0)
    
    # ✅ NUEVO: Sistema de trigger inmediato
    def _trigger_update(self, restaurante_id):
        """Notifica inmediatamente a todos los clientes conectados"""
        trigger_key = f"trigger_{restaurante_id}"
        self._event_triggers[trigger_key] = timezone.now()
    
    def check_trigger(self, restaurante_id, last_check):
        """Verifica si hay cambios desde la última verificación"""
        trigger_key = f"trigger_{restaurante_id}"
        last_trigger = self._event_triggers.get(trigger_key)
        return last_trigger and last_trigger > last_check

pedido_cache = PedidoMemoryCache.get_instance()

# core/views.py - SSE OPTIMIZADO
@require_GET
@login_required
def pedidos_sse(request, restaurante_id):
    """SSE MEJORADO - RESPONDE EN <1 SEGUNDO"""
    if request.user.id != int(restaurante_id) and not request.user.is_staff:
        return JsonResponse({'error': 'No autorizado'}, status=403)
    
    def event_stream():
        client_id = f"{restaurante_id}_{int(time.time())}"
        last_version = int(request.GET.get('version', 0))
        last_trigger = 0
        
        print(f"🚀 SSE CONECTADO para restaurante {restaurante_id}")
        
        try:
            # ✅ ENVIAR DATOS INMEDIATOS AL CONECTAR
            cache_data = ultra_cache.get_pedidos(restaurante_id)
            current_version = cache_data.get('version', 0)
            
            if cache_data['pedidos']:
                pedidos_serializados = []
                for pedido in cache_data['pedidos']:
                    pedido_data = pedido.copy()
                    if 'fecha' in pedido_data:
                        pedido_data['fecha'] = pedido_data['fecha'].isoformat()
                    pedidos_serializados.append(pedido_data)
                
                event_data = {
                    'type': 'pedidos_updated',
                    'pedidos': pedidos_serializados,
                    'version': current_version,
                    'timestamp': timezone.now().isoformat(),
                    'immediate': True
                }
                yield f"data: {json.dumps(event_data)}\n\n"
                print(f"📦 Datos INMEDIATOS enviados: {len(pedidos_serializados)} pedidos")
            
            # ✅ MONITOREAR CAMBIOS EN TIEMPO REAL
            while True:
                try:
                    current_time = timezone.now()
                    
                    # ✅ VERIFICACIÓN POR TRIGGER (MÁS RÁPIDO)
                    if ultra_cache.check_trigger(restaurante_id, last_trigger):
                        last_trigger = ultra_cache._triggers.get(restaurante_id, 0)
                        print(f"🎯 TRIGGER INMEDIATO detectado")
                        
                        cache_data = ultra_cache.get_pedidos(restaurante_id)
                        current_version = cache_data.get('version', 0)
                        
                        # Serializar rápidamente
                        pedidos_serializados = []
                        for pedido in cache_data['pedidos']:
                            pedido_data = pedido.copy()
                            if 'fecha' in pedido_data:
                                pedido_data['fecha'] = pedido_data['fecha'].isoformat()
                            pedidos_serializados.append(pedido_data)
                        
                        event_data = {
                            'type': 'pedidos_updated',
                            'pedidos': pedidos_serializados,
                            'version': current_version,
                            'timestamp': current_time.isoformat(),
                            'triggered': True
                        }
                        yield f"data: {json.dumps(event_data)}\n\n"
                        continue
                    
                    # ✅ VERIFICACIÓN POR VERSIÓN (FALLBACK)
                    cache_data = ultra_cache.get_pedidos(restaurante_id)
                    current_version = cache_data.get('version', 0)
                    
                    if current_version > last_version:
                        print(f"🔄 Cambio por VERSIÓN: {last_version} -> {current_version}")
                        
                        pedidos_serializados = []
                        for pedido in cache_data['pedidos']:
                            pedido_data = pedido.copy()
                            if 'fecha' in pedido_data:
                                pedido_data['fecha'] = pedido_data['fecha'].isoformat()
                            pedidos_serializados.append(pedido_data)
                        
                        event_data = {
                            'type': 'pedidos_updated',
                            'pedidos': pedidos_serializados,
                            'version': current_version,
                            'timestamp': current_time.isoformat()
                        }
                        yield f"data: {json.dumps(event_data)}\n\n"
                        
                        last_version = current_version
                    
                    # ✅ SLEEP OPTIMIZADO
                    time.sleep(0.3)  # 300ms - MÁS RÁPIDO
                    
                except Exception as e:
                    print(f"❌ Error en loop SSE: {str(e)}")
                    time.sleep(1)
                    
        except GeneratorExit:
            print(f"🔌 Cliente {client_id} desconectado")
        except Exception as e:
            logger.error(f"SSE error fatal: {str(e)}")
    
    response = StreamingHttpResponse(event_stream(), content_type='text/event-stream')
    response['Cache-Control'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no'
    return response

@require_GET
@login_required
def pedidos_polling(request, restaurante_id):
    """
    Fallback de polling para cuando SSE falla
    """
    if request.user.id != int(restaurante_id) and not request.user.is_staff:
        return JsonResponse({'error': 'No autorizado'}, status=403)
    
    version = int(request.GET.get('version', 0))
    current_version = pedido_cache.get_version(restaurante_id)
    
    if current_version > version:
        pedidos = pedido_cache.get_pedidos(restaurante_id)
        pedidos_serializados = []
        for pedido in pedidos:
            pedido_serializado = pedido.copy()
            if 'fecha' in pedido_serializado:  # ✅ CORREGIDO: pedido_serializado (sin 'd' extra)
                if not isinstance(pedido_serializado['fecha'], str):
                    pedido_serializado['fecha'] = pedido_serializado['fecha'].isoformat()
            pedidos_serializados.append(pedido_serializado)
        
        return JsonResponse({
            'pedidos': pedidos_serializados,
            'version': current_version
        })
    else:
        return JsonResponse({
            'pedidos': [],
            'version': current_version
        })

# ✅ REEMPLAZAR en actualizar_cache_pedidos
def actualizar_cache_pedidos(restaurante_id):
    """ACTUALIZACIÓN ULTRA-RÁPIDA DEL CACHE"""
    from .models import Pedido
    
    try:
        # ✅ CONSULTA MEGA-OPTIMIZADA
        pedidos_activos = Pedido.objects.filter(
            restaurante_id=restaurante_id,
            estado__in=['pendiente', 'en_preparacion', 'listo', 'procesando_pago']
        ).only(
            'id', 'numero_pedido', 'cliente', 'telefono', 'estado', 
            'fecha', 'total', 'metodo_pago', 'tipo_pedido', 'direccion'
        ).order_by('-fecha')[:50]
        
        # ✅ SERIALIZACIÓN EXPRÉS
        pedidos_data = []
        for pedido in pedidos_activos:
            pedidos_data.append({
                'id': pedido.id,
                'numero_pedido': pedido.numero_pedido,
                'cliente': pedido.cliente or 'Cliente',
                'telefono': pedido.telefono or 'Sin teléfono',
                'estado': pedido.estado,
                'fecha': pedido.fecha,
                'total': str(pedido.total) if pedido.total else '0.00',
                'metodo_pago': pedido.metodo_pago or 'efectivo',
                'tipo_pedido': pedido.tipo_pedido or 'retiro',
                'direccion': pedido.direccion or 'Retiro en local'
            })
        
        # ✅ ACTUALIZAR SOLO ULTRA_CACHE (ELIMINAR pedido_cache)
        ultra_cache.set_pedidos(restaurante_id, pedidos_data)
        
        print(f"⚡ CACHE ACTUALIZADO INSTANTÁNEAMENTE - Restaurante: {restaurante_id}, Pedidos: {len(pedidos_data)}")
        
    except Exception as e:
        print(f"❌ Error actualizando cache: {str(e)}")

@login_required
@never_cache
@no_cache_view
def lista_pedidos(request):
    # Use request.user directly, as it's a Restaurante instance
    restaurante = request.user
    # Verify that the user is active and a valid restaurant
    if not restaurante.is_active or not isinstance(restaurante, Restaurante):
        return render(request, 'error.html', {'mensaje': 'Usuario no es un restaurante válido'})

    # Get pedidos by status
    pedidos_pendientes = Pedido.objects.filter(restaurante=restaurante, estado='pendiente')
    pedidos_en_preparacion = Pedido.objects.filter(restaurante=restaurante, estado='en_preparacion')
    pedidos_listos = Pedido.objects.filter(restaurante=restaurante, estado='listo')

    # Use model choices for tiempos_estimados and motivos_cancelacion
    tiempos_estimados = Pedido.TIEMPO_ESTIMADO_CHOICES
    motivos_cancelacion = Pedido.MOTIVO_CANCELACION_CHOICES

    context = {
        'restaurante': restaurante,
        'pedidos_pendientes': pedidos_pendientes,
        'pedidos_en_preparacion': pedidos_en_preparacion,
        'pedidos_listos': pedidos_listos,
        'tiempos_estimados': tiempos_estimados,
        'motivos_cancelacion': motivos_cancelacion,
    }
    return render(request, 'core/lista_pedidos.html', context)

@login_required
@never_cache
@no_cache_view
def pedidos_pendientes_html(request):
    pedidos_pendientes = Pedido.objects.filter(
        restaurante=request.user,
        estado='pendiente'
    ).order_by('-fecha')
    response = render(request, 'core/pedidos_columnas.html', {
        'pedidos_pendientes': pedidos_pendientes,
        'pendientes_only': True,
        'tiempos_estimados': Pedido.TIEMPO_ESTIMADO_CHOICES,
        'motivos_cancelacion': Pedido.MOTIVO_CANCELACION_CHOICES
    })
    response['Cache-Control'] = 'no-store, no-cache, must-revalidate'
    return response

@login_required
@never_cache
@no_cache_view
def pedidos_en_preparacion_html(request):
    pedidos_en_preparacion = Pedido.objects.filter(
        restaurante=request.user,
        estado='en_preparacion'
    ).order_by('-fecha')
    return render(request, 'core/pedidos_columnas.html', {
        'pedidos_en_preparacion': pedidos_en_preparacion,
        'en_preparacion_only': True,
        'motivos_cancelacion': Pedido.MOTIVO_CANCELACION_CHOICES
    })

@login_required
@never_cache
@no_cache_view
def pedidos_listos_html(request):
    pedidos_listos = Pedido.objects.filter(
        restaurante=request.user,
        estado='listo'
    ).order_by('-fecha')
    return render(request, 'core/pedidos_columnas.html', {
        'pedidos_listos': pedidos_listos,
        'listos_only': True,
        'motivos_cancelacion': Pedido.MOTIVO_CANCELACION_CHOICES
    })

@login_required
@never_cache
@no_cache_view
def pedidos_cancelados(request):
    # Verificar y eliminar pedidos cancelados que hayan pasado las 3 horas
    now = timezone.now()
    limite_cancelados = now - timedelta(hours=3)
    Pedido.objects.filter(
        restaurante=request.user,
        estado='cancelado',
        fecha_cancelado__lt=limite_cancelados
    ).delete()

    pedidos = Pedido.objects.filter(
        restaurante=request.user,
        estado='cancelado',
    ).order_by('-fecha')
    return render(request, 'core/pedidos_cancelados.html', {
        'pedidos': pedidos,
        'restaurante': request.user  # Include restaurante for template
    })

@login_required
@never_cache
@no_cache_view
@require_POST
def eliminar_pedido(request, pedido_id):
    pedido = get_object_or_404(Pedido, id=pedido_id, restaurante=request.user)
    if pedido.estado not in ['cancelado', 'archivado']:
        return JsonResponse({'success': False, 'error': 'El pedido no está cancelado ni archivado'}, status=400)

    try:
        pedido_numero = pedido.numero_pedido
        pedido.delete()
        
        # ✅ ACTUALIZACIÓN INMEDIATA
        print(f"⚡ Pedido #{pedido_numero} ELIMINADO, ACTUALIZACIÓN INMEDIATA...")
        actualizar_cache_pedidos(request.user.id)
        
        return JsonResponse({'success': True, 'message': f'Pedido #{pedido_numero} eliminado correctamente'})
    except Exception as e:
        logger.error(f"Error al eliminar pedido {pedido_id}: {str(e)}")
        return JsonResponse({'success': False, 'error': f'Error al eliminar el pedido: {str(e)}'}, status=500)

@login_required
@require_POST
@never_cache
@no_cache_view
def marcar_en_entrega(request, pedido_id):
    pedido = get_object_or_404(Pedido, id=pedido_id, restaurante=request.user)
    if pedido.estado != 'listo':
        return JsonResponse({'success': False, 'error': 'El pedido no está listo para entrega'})

    pedido.estado = 'en_entrega'
    pedido.fecha_en_entrega = timezone.now()
    pedido.save()
    
    # ✅ ACTUALIZACIÓN INMEDIATA CON CONFIRMACIÓN
    print(f"⚡ Pedido #{pedido.numero_pedido} marcado como EN ENTREGA, ACTUALIZACIÓN INMEDIATA...")
    actualizar_cache_pedidos(request.user.id)
    
    # ✅ NUEVO: Esperar un momento para asegurar la actualización
    import time
    time.sleep(0.1)
    
    return JsonResponse({'success': True})

@login_required
@require_POST
@never_cache
@no_cache_view
def archivar_pedido(request, pedido_id):
    pedido = get_object_or_404(Pedido, id=pedido_id, restaurante=request.user)
    if pedido.estado not in ['listo', 'en_entrega']:
        return JsonResponse({'success': False, 'error': 'El pedido no puede ser archivado'})

    pedido.estado = 'archivado'
    pedido.save()
    
    # ✅ ACTUALIZACIÓN INMEDIATA CON CONFIRMACIÓN
    print(f"⚡ Pedido #{pedido.numero_pedido} ARCHIVADO, ACTUALIZACIÓN INMEDIATA...")
    actualizar_cache_pedidos(request.user.id)
    
    # ✅ NUEVO: Esperar un momento para asegurar la actualización
    import time
    time.sleep(0.1)
    
    return JsonResponse({'success': True})

@login_required
@require_POST
@never_cache
@no_cache_view
def actualizar_estado(request, pedido_id):
    pedido = get_object_or_404(Pedido, id=pedido_id, restaurante=request.user)
    estado = request.POST.get('estado')
    if estado not in ['listo']:
        return JsonResponse({'success': False, 'error': 'Estado no válido'})

    pedido.estado = estado
    pedido.save()
    
    # ✅ ACTUALIZACIÓN INMEDIATA CON CONFIRMACIÓN
    print(f"⚡ Pedido #{pedido.numero_pedido} actualizado a {estado.upper()}, ACTUALIZACIÓN INMEDIATA...")
    actualizar_cache_pedidos(request.user.id)
    
    # ✅ NUEVO: Esperar un momento para asegurar la actualización
    import time
    time.sleep(0.1)
    
    return JsonResponse({'success': True})

@login_required
@never_cache
@no_cache_view
def pedidos_en_entrega(request):
    # Verificar y archivar pedidos en entrega que hayan pasado 1 hora
    now = timezone.now()
    limite_entrega = now - timedelta(hours=1)
    pedidos_a_archivar = Pedido.objects.filter(
        restaurante=request.user,
        estado='en_entrega',
        fecha_en_entrega__lt=limite_entrega,
        direccion__isnull=False
    ).exclude(direccion='Retiro en local')
    for pedido in pedidos_a_archivar:
        pedido.estado = 'archivado'
        pedido.save()

    pedidos = Pedido.objects.filter(
        restaurante=request.user,
        estado='en_entrega',
        direccion__isnull=False
    ).exclude(direccion='Retiro en local').order_by('-fecha')
    return render(request, 'core/entrega.html', {
        'pedidos': pedidos,
        'restaurante': request.user
    })


month_names_es = [
    "", 
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"
]

@login_required
@never_cache
@no_cache_view
def todos_pedidos(request):
    pedidos = Pedido.objects.filter(
        restaurante=request.user,
        estado='archivado'
    ).order_by('-fecha')

    # Agrupar pedidos por año y mes
    pedidos_by_month = {}
    for year, year_group in groupby(pedidos, key=lambda x: x.fecha.year):
        for month, month_group in groupby(sorted(year_group, key=lambda x: x.fecha.month, reverse=True), key=lambda x: x.fecha.month):
            month_key = f"{year}-{month:02d}"
            pedidos_by_month[month_key] = {
                'year': year,
                'month': month,
                'month_name': month_names_es[month],  # Usar la lista en español
                'pedidos': list(month_group)
            }

    # Ordenar meses en orden descendente (más reciente primero)
    sorted_months = sorted(pedidos_by_month.items(), key=lambda x: x[0], reverse=True)

    return render(request, 'core/todos_pedidos.html', {
        'pedidos_by_month': sorted_months,
        'restaurante': request.user
    })

@login_required
@require_POST
@never_cache
@no_cache_view
def aceptar_pedido(request, pedido_id):
    pedido = get_object_or_404(Pedido, id=pedido_id, restaurante=request.user)
    if pedido.estado != 'pendiente':
        return JsonResponse({'success': False, 'error': 'El pedido no está pendiente'})

    tiempo_estimado = request.POST.get('tiempo_estimado')
    if not tiempo_estimado or tiempo_estimado not in dict(Pedido.TIEMPO_ESTIMADO_CHOICES):
        return JsonResponse({'success': False, 'error': 'Tiempo estimado inválido'})

    pedido.estado = 'en_preparacion'
    pedido.tiempo_estimado = tiempo_estimado
    pedido.save()
    
    # ✅ ACTUALIZACIÓN ULTRA-RÁPIDA CON CONFIRMACIÓN
    print(f"⚡ Pedido #{pedido.numero_pedido} ACEPTADO - Actualizando cache...")
    actualizar_cache_pedidos(request.user.id)
    
    # ✅ NUEVO: Esperar un momento para asegurar la actualización
    import time
    time.sleep(0.1)
    
    return JsonResponse({'success': True})

@login_required
@require_POST
@never_cache
@no_cache_view
def rechazar_pedido(request, pedido_id):
    pedido = get_object_or_404(Pedido, id=pedido_id, restaurante=request.user)
    motivo = request.POST.get('motivo')
    if not motivo or motivo not in dict(Pedido.MOTIVO_CANCELACION_CHOICES):
        return JsonResponse({'success': False, 'error': 'Motivo de cancelación inválido'})

    pedido.estado = 'cancelado'
    pedido.motivo_cancelacion = motivo
    pedido.fecha_cancelado = timezone.now()
    pedido.save()
    
    # ✅ ACTUALIZAR CACHE INMEDIATAMENTE CON CONFIRMACIÓN
    print(f"🔄 Pedido #{pedido.numero_pedido} rechazado, actualizando cache...")
    actualizar_cache_pedidos(request.user.id)
    
    # ✅ NUEVO: Esperar un momento para asegurar la actualización
    import time
    time.sleep(0.1)
    
    return JsonResponse({'success': True})



@login_required
@never_cache
@no_cache_view
def pedido_json(request, pedido_id):
    pedido = get_object_or_404(Pedido, id=pedido_id, restaurante=request.user)
    items = [
        {
            'nombre_producto': item.nombre_producto,
            'cantidad': item.cantidad,
            'precio_unitario': str(item.precio_unitario),
            'subtotal': item.subtotal,
            'opciones_seleccionadas': [
                {
                    'nombre': opcion.get('nombre', ''),
                    'precio_adicional': str(opcion.get('precio_adicional', '0.00'))
                }
                for opcion in item.opciones_seleccionadas
            ] if item.opciones_seleccionadas else [],
            # Include the original filename from the product's image field
            'imagen_nombre_original': item.producto.imagen.name.split('/')[-1] if item.producto and item.producto.imagen else 'default.png'
        }
        for item in pedido.items.all()
    ]
    # Calculate subtotal from items if not stored
    subtotal = Decimal(pedido.subtotal or sum(item['subtotal'] for item in items))
    # Calculate adjusted subtotal (after cash discount)
    monto_descuento_efectivo = Decimal('0.00')
    if pedido.cash_discount_applied and pedido.cash_discount_percentage > 0:
        monto_descuento_efectivo = subtotal * (Decimal(pedido.cash_discount_percentage) / 100)
    subtotal_ajustado = subtotal - monto_descuento_efectivo
    # Calculate code discount
    monto_descuento_codigo = Decimal('0.00')
    if pedido.codigo_descuento:
        codigos = pedido.restaurante.codigos_descuento or []
        for codigo in codigos:
            if codigo['nombre'] == pedido.codigo_descuento:
                porcentaje = Decimal(str(codigo['porcentaje']))
                monto_descuento_codigo = subtotal_ajustado * (porcentaje / 100)
                break
    data = {
        'id': pedido.id,
        'numero_pedido': pedido.numero_pedido,
        'nombre_cliente': pedido.cliente or 'Sin nombre',
        'telefono_cliente': pedido.telefono or 'Sin teléfono',
        'direccion_entrega': pedido.direccion or 'Retiro en local',
        'metodo_pago': pedido.metodo_pago or 'efectivo',
        'tipo_pedido': pedido.tipo_pedido or 'retiro',
        'subtotal': str(subtotal),
        'costo_envio': str(pedido.costo_envio or 0),
        'monto_descuento': str(pedido.monto_descuento or 0),
        'monto_descuento_codigo': str(monto_descuento_codigo),
        'monto_descuento_efectivo': str(monto_descuento_efectivo),
        'subtotal_ajustado': str(subtotal_ajustado),
        'total': str(pedido.total or 0),
        'aclaraciones': pedido.aclaraciones or 'Sin aclaraciones',
        'estado': pedido.get_estado_display() or 'Sin estado',
        'fecha_creacion': pedido.fecha.isoformat() if pedido.fecha else '',
        'tiempo_estimado': pedido.tiempo_estimado or 'Sin tiempo estimado',
        'items': [
            {**item, 'subtotal': str(item['subtotal'])} for item in items
        ],
        # Use restaurante.username instead of nombre_local for path consistency
        'restaurante_nombre': pedido.restaurante.username
    }
    return JsonResponse(data)

def rate_limit_check(ip_address, key, limit, window=60):
    """
    Verifica si se excedió el límite de requests
    key: identificador único (ej: 'procesar_pedido')
    limit: máximo de requests por ventana de tiempo
    window: ventana de tiempo en segundos (default 60s)
    """
    cache_key = f"rate_limit:{key}:{ip_address}"
    current = cache.get(cache_key, 0)
    
    if current >= limit:
        return False
    
    cache.set(cache_key, current + 1, window)
    return True

@never_cache
@no_cache_view
def restaurante_publico(request, nombre_restaurante):
    reserved_paths = ['panel', 'login', 'registro', 'logout', 'admin']
    if nombre_restaurante.lower() in reserved_paths:
        return redirect('home')

    restaurante = get_object_or_404(Restaurante, username=nombre_restaurante, activo=True)
    restaurante.refresh_from_db()

    if request.method == 'POST':
        return procesar_pedido(request, restaurante)

    # ✅ CACHE ESTRATÉGICO - REEMPLAZAR LA CONSULTA ACTUAL
    cache_key = f'restaurante_menu_{nombre_restaurante}'
    categorias = cache.get(cache_key)
    
    if not categorias:
        # Solo hacemos la consulta a BD si no está en cache
        categorias = Categoria.objects.filter(restaurante=restaurante).prefetch_related(
            Prefetch('producto_set', 
                    queryset=Producto.objects.filter(disponible=True).order_by('nombre'))
        )
        # Guardar en cache por 10 minutos
        cache.set(cache_key, categorias, 60 * 10)
    
    # Invalidar cache cuando cambie el menú (agregar en otras vistas)
    # Ej: cuando edites/agregues/elimines productos

    response = render(request, 'core/restaurante_publico.html', {
        'restaurante': restaurante,
        'categorias': categorias,
        'color_principal': restaurante.color_principal or '#A3E1BE',
    })

    response['Cache-Control'] = 'no-store, no-cache, must-revalidate, proxy-revalidate'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    return response


@login_required
@never_cache
@no_cache_view
def pedidos_procesando_pagos_html(request):
    # Clean up orders in 'error_pago' state older than 30 minutes
    now = timezone.now()
    limite_error_pago = now - timedelta(minutes=30)
    deleted_count = Pedido.objects.filter(
        restaurante=request.user,
        estado='error_pago',
        fecha_error_pago__lt=limite_error_pago
    ).delete()[0]
    logger.info(f"Deleted {deleted_count} error_pago orders older than 30 minutes for restaurante {request.user.id}")

    # Fetch orders in procesando_pago state
    pedidos_procesando = Pedido.objects.filter(
        restaurante=request.user,
        estado='procesando_pago'
    ).order_by('-fecha')
    logger.info(f"Procesando_pago orders: {list(pedidos_procesando.values('id', 'numero_pedido', 'estado'))}")

    # Fetch orders in error_pago state
    pedidos_error = Pedido.objects.filter(
        restaurante=request.user,
        estado='error_pago'
    ).order_by('-fecha')
    logger.info(f"Error_pago orders: {list(pedidos_error.values('id', 'numero_pedido', 'estado', 'fecha_error_pago'))}")

    # Debug: Check for overlap
    overlap_ids = set(pedidos_procesando.values_list('id', flat=True)) & set(pedidos_error.values_list('id', flat=True))
    if overlap_ids:
        logger.warning(f"Overlap detected between procesando_pago and error_pago: {overlap_ids}")

    context = {
        'restaurante': request.user,
        'pedidos_procesando': pedidos_procesando,
        'pedidos_error': pedidos_error,
    }
    return render(request, 'core/pedidos_procesando_pago.html', context)

@login_required
@never_cache
@no_cache_view
@require_POST
def confirmar_pago(request, pedido_id):
    pedido = get_object_or_404(Pedido, token=pedido_id, restaurante=request.user)
    if pedido.estado != 'procesando_pago':
        return JsonResponse({'success': False, 'error': 'El pedido no está en estado de procesamiento de pago'}, status=400)

    pedido.estado = 'pendiente'
    pedido.save()

    # ✅ ACTUALIZACIÓN INMEDIATA
    print(f"⚡ Pago CONFIRMADO para pedido #{pedido.numero_pedido}, ACTUALIZACIÓN INMEDIATA...")
    actualizar_cache_pedidos(request.user.id)
    
    return JsonResponse({'success': True})

@login_required
@never_cache
@no_cache_view
@require_POST
def rechazar_pago(request, pedido_id):
    pedido = get_object_or_404(Pedido, id=pedido_id, restaurante=request.user)
    if pedido.estado != 'procesando_pago':
        return JsonResponse({'success': False, 'error': 'El pedido no está en estado de procesamiento de pago'}, status=400)

    motivo_error = request.POST.get('motivo_error', 'Error desconocido en el procesamiento del pago')
    pedido.estado = 'error_pago'
    pedido.motivo_error_pago = motivo_error
    pedido.fecha_error_pago = timezone.now()
    pedido.save()

    # ✅ ACTUALIZACIÓN INMEDIATA
    print(f"⚡ Pago RECHAZADO para pedido #{pedido.numero_pedido}, ACTUALIZACIÓN INMEDIATA...")
    actualizar_cache_pedidos(request.user.id)
    
    return JsonResponse({'success': True})

# Update procesar_pedido to handle Mercado Pago orders
def procesar_pedido(request, restaurante):
    if request.method == 'POST':
        try:
            with transaction.atomic():
                restaurante = get_object_or_404(Restaurante, username=restaurante)
                if not restaurante.esta_abierto:
                    return JsonResponse({'error': 'El restaurante está cerrado.'}, status=400)

                # Extract datos_cliente
                datos_cliente_raw = request.POST.get('datos_cliente', '')
                if isinstance(datos_cliente_raw, list):
                    datos_cliente_raw = datos_cliente_raw[0]
                try:
                    datos_cliente = json.loads(datos_cliente_raw) if datos_cliente_raw else {}
                except json.JSONDecodeError:
                    return JsonResponse({'error': 'Formato de datos_cliente inválido.'}, status=400)

                nombre = datos_cliente.get('nombre', '').strip()
                telefono = datos_cliente.get('telefono', '').strip()
                direccion = datos_cliente.get('direccion', '').strip()
                aclaraciones = datos_cliente.get('aclaraciones', '').strip()
                metodo_pago = datos_cliente.get('metodo_pago', 'efectivo')

                # Validate required fields
                if not nombre:
                    return JsonResponse({'error': 'El nombre del cliente es requerido.'}, status=400)
                if not telefono:
                    return JsonResponse({'error': 'El teléfono del cliente es requerido.'}, status=400)

                # === MODIFICACIÓN 1: Validar métodos de pago habilitados ===
                if metodo_pago == 'mercadopago' and not restaurante.metodo_pago_mercadopago:
                    return JsonResponse({'error': 'El restaurante no tiene habilitado Mercado Pago.'}, status=400)
                
                if metodo_pago == 'alias' and not restaurante.metodo_pago_alias:
                    return JsonResponse({'error': 'El restaurante no tiene habilitado el pago por transferencia.'}, status=400)
                
                if metodo_pago == 'alias' and not restaurante.alias_cbu:
                    return JsonResponse({'error': 'El restaurante no tiene configurado el alias/CBU para transferencias.'}, status=400)
                
                if metodo_pago == 'mercadopago' and not restaurante.mp_access_token:
                    return JsonResponse({'error': 'El restaurante no tiene cuenta de Mercado Pago vinculada.'}, status=400)

                # Extract productos
                productos_raw = request.POST.get('productos', '')
                if isinstance(productos_raw, list):
                    productos_raw = productos_raw[0]
                try:
                    productos = json.loads(productos_raw) if productos_raw else []
                except json.JSONDecodeError:
                    return JsonResponse({'error': 'Formato de productos inválido.'}, status=400)

                productos_disponibles = {
                    str(p.id): p for p in Producto.objects.filter(
                        restaurante=restaurante, disponible=True, agotado=False
                    )
                }
                subtotal = Decimal('0.00')
                items_pedido = []

                for item in productos:
                    producto_id = str(item.get('id'))
                    cantidad = int(item.get('cantidad', 1))
                    if cantidad > 0 and producto_id in productos_disponibles:
                        producto = productos_disponibles[producto_id]
                        opciones_seleccionadas = item.get('opciones', [])
                        precio_total = Decimal(str(item.get('precio_unitario', producto.precio)))

                        if not producto.reducir_stock(cantidad):
                            raise ValueError(f"No hay stock de {producto.nombre}")
                        subtotal += precio_total * cantidad
                        items_pedido.append({
                            'producto': producto,
                            'cantidad': cantidad,
                            'precio_unitario': precio_total,
                            'opciones_seleccionadas': opciones_seleccionadas
                        })

                if not items_pedido:
                    return JsonResponse({'error': 'No se seleccionaron productos.'}, status=400)

                # Handle discounts
                codigo_descuento = request.POST.get('codigo_descuento', '')
                if isinstance(codigo_descuento, list):
                    codigo_descuento = codigo_descuento[0].strip().upper() if codigo_descuento else ''
                else:
                    codigo_descuento = codigo_descuento.strip().upper()

                monto_descuento = Decimal('0.00')
                monto_descuento_codigo = Decimal('0.00')
                monto_descuento_efectivo = Decimal('0.00')
                cash_discount_applied = False

                subtotal_ajustado = subtotal
                if metodo_pago == 'efectivo' and restaurante.cash_discount_enabled and restaurante.cash_discount_percentage > 0:
                    cash_discount_porcentaje = Decimal(str(restaurante.cash_discount_percentage))
                    monto_descuento_efectivo = subtotal * (cash_discount_porcentaje / 100)
                    subtotal_ajustado -= monto_descuento_efectivo
                    monto_descuento += monto_descuento_efectivo
                    cash_discount_applied = True

                if codigo_descuento:
                    codigos = restaurante.codigos_descuento or []
                    for codigo in codigos:
                        if codigo['nombre'] == codigo_descuento and codigo.get('activo', True):
                            if codigo.get('usos_actuales', 0) < codigo.get('usos_maximos', float('inf')):
                                porcentaje = Decimal(str(codigo['porcentaje']))
                                monto_descuento_codigo = subtotal_ajustado * (porcentaje / 100)
                                monto_descuento += monto_descuento_codigo
                                codigo['usos_actuales'] = codigo.get('usos_actuales', 0) + 1
                                restaurante.save()
                                break
                    else:
                        return JsonResponse({'error': 'El código de descuento no existe o no es válido.'}, status=400)

                costo_envio = Decimal('0.00')
                tipo_pedido = request.POST.get('tipo_pedido', 'retiro')
                if isinstance(tipo_pedido, list):
                    tipo_pedido = tipo_pedido[0] if tipo_pedido else 'retiro'

                if tipo_pedido == 'delivery':
                    costo_envio = restaurante.costo_envio or Decimal('0.00')
                    if restaurante.umbral_envio_gratis and subtotal >= restaurante.umbral_envio_gratis:
                        costo_envio = Decimal('0.00')
                    if not direccion:
                        return JsonResponse({'error': 'La dirección es requerida para delivery.'}, status=400)
                else:
                    direccion = 'Retiro en local'

                # Set estado based on payment method
                if metodo_pago == 'mercadopago':
                    estado = 'procesando_pago'
                elif metodo_pago == 'alias':
                    estado = 'pendiente'  # Mismo estado que efectivo
                else:
                    estado = 'pendiente'  # efectivo

                # Create the order
                pedido = Pedido.objects.create(
                    restaurante=restaurante,
                    cliente=nombre,
                    telefono=telefono,
                    direccion=direccion,
                    metodo_pago=metodo_pago,
                    tipo_pedido=tipo_pedido,
                    subtotal=subtotal,
                    costo_envio=costo_envio,
                    monto_descuento=monto_descuento,
                    total=subtotal_ajustado - monto_descuento_codigo + costo_envio,
                    aclaraciones=aclaraciones,
                    estado=estado,
                    codigo_descuento=codigo_descuento if codigo_descuento and monto_descuento_codigo > 0 else None,
                    cash_discount_applied=cash_discount_applied,
                    cash_discount_percentage=restaurante.cash_discount_percentage if cash_discount_applied else 0
                )

                # Create order items
                for item in items_pedido:
                    ItemPedido.objects.create(
                        pedido=pedido,
                        nombre_producto=item['producto'].nombre,
                        producto=item['producto'],
                        cantidad=item['cantidad'],
                        precio_unitario=item['precio_unitario'],
                        opciones_seleccionadas=item['opciones_seleccionadas']
                    )
                print(f"⚡ NUEVO PEDIDO CREADO: #{pedido.numero_pedido}, ACTUALIZACIÓN INMEDIATA...")
                actualizar_cache_pedidos(restaurante.id)

                return JsonResponse({
                    'success': True,
                    'redirect_url': pedido.get_absolute_url()
                })
        except Exception as e:
            logger.error(f"Error en procesar_pedido: {str(e)}")
            return JsonResponse({'error': str(e)}, status=400)
    return JsonResponse({'error': 'Método no permitido'}, status=405)

@never_cache
@no_cache_view
@csrf_protect
def validar_codigo_descuento(request, nombre_restaurante):
    logger.info(f"Validar código descuento llamado para restaurante: {nombre_restaurante}")
    if request.method != 'POST':
        logger.error("Método no permitido")
        return JsonResponse({'valid': False, 'error': 'Método no permitido'}, status=405)

    restaurante = get_object_or_404(Restaurante, username=nombre_restaurante, activo=True)
    codigo = request.POST.get('codigo', '').strip().upper()
    logger.info(f"Verificando código: {codigo}")

    if not codigo:
        logger.warning("Código vacío recibido")
        return JsonResponse({'valid': False, 'error': 'Código requerido'}, status=400)

    codigos = restaurante.codigos_descuento or []
    if not isinstance(codigos, list):
        logger.error("codigos_descuento no es una lista válida")
        return JsonResponse({'valid': False, 'error': 'Error interno del servidor'}, status=500)

    for c in codigos:
        if not isinstance(c, dict):
            logger.warning(f"Entrada de código inválida: {c}")
            continue
        if c.get('nombre', '').upper() == codigo and c.get('activo', True):
            usos_actuales = c.get('usos_actuales', 0)
            usos_maximos = c.get('usos_maximos', float('inf'))
            porcentaje = c.get('porcentaje', 0)
            if usos_actuales < usos_maximos and porcentaje > 0:
                logger.info(f"Código válido encontrado: {codigo}, porcentaje: {porcentaje}")
                return JsonResponse({
                    'valid': True,
                    'porcentaje': float(porcentaje)
                })

    logger.warning(f"Código no válido o no encontrado: {codigo}")
    return JsonResponse({
        'valid': False,
        'error': 'Código no válido o no disponible'
    }, status=400)

@login_required
@never_cache
@no_cache_view
def vincular_mercado_pago(request):
    app_id = settings.MERCADO_PAGO_APP_ID
    # Generar code_verifier (string aleatorio de 43-128 caracteres)
    code_verifier = base64.urlsafe_b64encode(os.urandom(32)).decode('utf-8').rstrip('=')
    # Generar code_challenge (SHA-256 del code_verifier)
    code_challenge = base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode('utf-8')).digest()).decode('utf-8').rstrip('=')
    # Almacenar code_verifier en la sesión
    request.session['mp_code_verifier'] = code_verifier
    if settings.DEBUG:
        redirect_uri = request.build_absolute_uri(reverse('mercado_pago_callback'))
    else:
        redirect_uri = f"https://piattoweb.com{reverse('mercado_pago_callback')}"
    auth_url = (
        f"https://auth.mercadopago.com.ar/authorization?"
        f"client_id={app_id}&"
        f"response_type=code&"
        f"redirect_uri={redirect_uri}&"
        f"code_challenge={code_challenge}&"
        f"code_challenge_method=S256"
    )
    logger.info(f"Generando URL de autorización con redirect_uri: {redirect_uri}, code_challenge: {code_challenge}")
    return redirect(auth_url)

@login_required
@never_cache
@no_cache_view
def mercado_pago_callback(request):
    logger.info(f"Callback recibido con GET: {request.GET}")
    code = request.GET.get('code')
    if not code:
        logger.error("No se recibió el código de autorización")
        messages.error(request, 'Error en la vinculación de Mercado Pago.')
        return redirect('configuraciones')

    code_verifier = request.session.get('mp_code_verifier')
    if not code_verifier:
        logger.error("No se encontró code_verifier en la sesión")
        messages.error(request, 'Error interno al procesar la vinculación.')
        return redirect('configuraciones')

    url = "https://api.mercadopago.com/oauth/token"
    redirect_uri = request.build_absolute_uri(reverse('mercado_pago_callback'))
    logger.info(f"Enviando solicitud a Mercado Pago con redirect_uri: {redirect_uri}, code_verifier: {code_verifier}")
    data = {
        'client_id': settings.MERCADO_PAGO_APP_ID,
        'client_secret': settings.MERCADO_PAGO_CLIENT_SECRET,
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': redirect_uri,
        'code_verifier': code_verifier
    }
    response = requests.post(url, data=data)
    logger.info(f"Respuesta de Mercado Pago: status={response.status_code}, texto={response.text}")
    if response.status_code == 200:
        try:
            token_data = response.json()
            logger.info(f"Datos de token recibidos: {token_data}")
            restaurante = request.user
            restaurante.mp_access_token = token_data.get('access_token')
            restaurante.mp_refresh_token = token_data.get('refresh_token')
            restaurante.mp_user_id = str(token_data.get('user_id', ''))
            restaurante.mp_token_expires_at = timezone.now() + timedelta(seconds=token_data.get('expires_in', 0))
            restaurante.save()
            # Limpiar code_verifier de la sesión después de usarlo
            del request.session['mp_code_verifier']
            logger.info(f"Tokens guardados para restaurante {restaurante.id}")
            messages.success(request, 'Cuenta de Mercado Pago vinculada correctamente.')
        except (KeyError, ValueError) as e:
            logger.error(f"Error al procesar token_data: {str(e)}")
            messages.error(request, 'Error al procesar los datos de Mercado Pago.')
    else:
        logger.error(f"Error en la API de Mercado Pago: {response.text}")
        messages.error(request, 'Error al obtener los tokens de Mercado Pago.')
    return redirect('configuraciones')

@login_required
@require_POST
@never_cache
@no_cache_view
def desvincular_mercado_pago(request):
    restaurante = request.user
    restaurante.mp_access_token = None
    restaurante.mp_refresh_token = None
    restaurante.mp_user_id = None
    restaurante.mp_token_expires_at = None
    restaurante.save()
    messages.success(request, 'Cuenta de Mercado Pago desvinculada correctamente.')
    return redirect('configuraciones')


def get_mp_access_token(restaurante):
    if not restaurante.mp_access_token:
        raise ValueError("No hay cuenta de Mercado Pago vinculada.")
    if restaurante.mp_token_expires_at > timezone.now() + timedelta(minutes=5):
        return restaurante.mp_access_token
    else:
        url = "https://api.mercadopago.com/oauth/token"
        data = {
            'client_id': settings.MERCADO_PAGO_APP_ID,
            'client_secret': settings.MERCADO_PAGO_CLIENT_SECRET,
            'grant_type': 'refresh_token',
            'refresh_token': restaurante.mp_refresh_token
        }
        response = requests.post(url, data=data)
        if response.status_code == 200:
            token_data = response.json()
            restaurante.mp_access_token = token_data['access_token']
            restaurante.mp_refresh_token = token_data.get('refresh_token', restaurante.mp_refresh_token)
            restaurante.mp_token_expires_at = timezone.now() + timedelta(seconds=token_data['expires_in'])
            restaurante.save()
            return token_data['access_token']
        else:
            raise ValueError("Error al refrescar el token de Mercado Pago.")

@never_cache
@no_cache_view
@csrf_protect
def confirmacion_pedido(request, nombre_restaurante, token):
    status = request.GET.get("status", None)
    external_reference = request.GET.get("external_reference", None)

    logger.info(f"Confirmación para pedido {external_reference}, estado {status}")

    try:
        pedido = get_object_or_404(Pedido, token=token, restaurante__username=nombre_restaurante)

        if pedido.metodo_pago == 'alias':
            params = {
                'pedido': pedido,
                'restaurante': pedido.restaurante,
                'color_principal': pedido.restaurante.color_principal or '#A3E1BE',
                'confirmado': True,
                'init_point': None,
                'alias': True  # Nuevo parámetro para identificar pago por alias
            }
            logger.info(f"Rendering confirmation page for ALIAS pedido {pedido.numero_pedido}")
            return render(request, 'core/confirmacion_pedido.html', params)
        
        # SOLO PARA EFECTIVO - condición corregida
        if pedido.metodo_pago == 'efectivo':
            params = {
                'pedido': pedido,
                'restaurante': pedido.restaurante,
                'color_principal': pedido.restaurante.color_principal or '#A3E1BE',
                'confirmado': True,
                'init_point': None,
                'efectivo': True
            }
            logger.info(f"Rendering confirmation page for EFECTIVO pedido {pedido.numero_pedido}")
            return render(request, 'core/confirmacion_pedido.html', params)

        items = get_list_or_404(ItemPedido, pedido=pedido)

        for item in items:
            if not isinstance(item.precio_unitario, (int, float, Decimal)) or item.precio_unitario <= 0:
                logger.error(f"Invalid precio_unitario for item {item.nombre_producto}: {item.precio_unitario}")
                return JsonResponse({'error': 'Invalid item price'}, status=400)

        # Preparar items para Mercado Pago
        mp_items = []
        for i in items:
            mp_item = {
                "id": str(i.producto.id) if i.producto else str(i.id),
                "title": i.nombre_producto,
                "description": i.producto.descripcion[:500] if i.producto and i.producto.descripcion else "Sin descripción",
                "category_id": "food",
                "quantity": i.cantidad,
                "unit_price": float(i.precio_unitario)
            }
            mp_items.append(mp_item)

        if pedido.costo_envio and pedido.costo_envio > 0:
            mp_items.append({
                "id": "shipping",
                "title": "Costo de envío",
                "description": "Costo de envío del pedido",
                "category_id": "shipping",
                "quantity": 1,
                "unit_price": float(pedido.costo_envio)
            })

        total_descuento = Decimal('0.00')
        if pedido.monto_descuento:
            total_descuento += pedido.monto_descuento  

        if total_descuento > 0:
            mp_items.append({
                "id": "discount",
                "title": "Descuento",
                "description": "Descuento aplicado al pedido",
                "category_id": "discount",
                "quantity": 1,
                "unit_price": -float(total_descuento)
            })

        # Obtener datos del payer desde el pedido
        payer_info = {
            "name": pedido.cliente.split()[0] if pedido.cliente else "Cliente",
            "surname": " ".join(pedido.cliente.split()[1:]) if pedido.cliente and len(pedido.cliente.split()) > 1 else "Sin apellido",
            "email": "cliente@example.com",
            "phone": {
                "area_code": "11",
                "number": pedido.telefono[-8:] if pedido.telefono and len(pedido.telefono) >= 8 else "12345678"
            }
        }

        # Construir el cuerpo de la preferencia
        body = {
            "items": mp_items,
            "payer": payer_info,
            "back_urls": {
                "success": f"https://{request.get_host()}/hello",
                "failure": f"https://{request.get_host()}/hello",
                "pending": f"https://{request.get_host()}/hello"
            },
            "auto_return": "approved",
            "external_reference": str(pedido.token),
            "notification_url": f"https://{request.get_host()}/hello",
            "statement_descriptor": f"PIATTO {pedido.restaurante.nombre_local[:12]}",
        }

        log_body = body.copy()
        log_body['external_reference'] = str(log_body['external_reference'])
        logger.info(f"Sending request to Mercado Pago: {json.dumps(log_body, indent=2)}")

        access_token = get_mp_access_token(pedido.restaurante)
        headers = {"Authorization": f"Bearer {access_token}"}

        response = requests.post("https://api.mercadopago.com/checkout/preferences", json=body, headers=headers)

        if not response.ok:
            logger.error(f"Mercado Pago API error: Status {response.status_code}, Response: {response.text}")
            return JsonResponse({'error': 'Failed to create payment preference'}, status=500)

        try:
            data = response.json()
        except ValueError:
            logger.error(f"Invalid JSON response from Mercado Pago: {response.text}")
            return JsonResponse({'error': 'Invalid response from payment provider'}, status=500)

        init_point = data.get('init_point', None)
        if not init_point:
            logger.error(f"No init_point in Mercado Pago response: {json.dumps(data, indent=2)}")
            return JsonResponse({'error': 'Failed to retrieve payment link'}, status=500)

        pedido.init_point = init_point
        pedido.save()

        if status is None:
            return JsonResponse({'init_point': init_point})

        params = {
            'pedido': pedido,
            'restaurante': pedido.restaurante,
            'color_principal': pedido.restaurante.color_principal or '#A3E1BE',
            'confirmado': status == "approved",
            'init_point': init_point
        }

        if status in ["pending", "in_process"]:
            params['confirmado'] = False

        if status in ["cancelled", "rejected"]:
            params['confirmado'] = False
            params['error'] = True

        logger.info(f"Rendering confirmation page for pedido {pedido.numero_pedido} with init_point: {init_point}")
        return render(request, 'core/confirmacion_pedido.html', params)

    except ValueError as ve:
        logger.error(f"Error de token en confirmacion_pedido: {str(ve)}")
        return JsonResponse({'error': 'No se pudo procesar el pago: cuenta de Mercado Pago no vinculada o token inválido.'}, status=400)
    except Exception as e:
        logger.error(f"Unexpected error in confirmacion_pedido: {str(e)}", exc_info=True)
        return JsonResponse({'error': 'Internal server error'}, status=500)

@login_required
@never_cache
@no_cache_view
def imprimir_ticket(request, pedido_id):
    pedido = get_object_or_404(Pedido, id=pedido_id, restaurante=request.user)

    # Marcar como impreso
    pedido.impreso = True
    pedido.save()

    # Configurar respuesta PDF con tamaño de ticket (80mm de ancho)
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'filename=ticket_pedido_{pedido.numero_pedido}.pdf'

    # Tamaño de ticket estándar (80mm x aprox 200mm)
    # Convertir mm a puntos (1mm = 2.83465 puntos)
    ticket_width = 80 * 2.83465
    ticket_height = 100 * 2.83465  # Alto de página A4 pero se cortará
    
    # Crear PDF con tamaño de ticket
    p = canvas.Canvas(response, pagesize=(ticket_width, ticket_height))
    
    # Configurar márgenes
    margin_left = 10
    margin_right = ticket_width - 10
    current_y = ticket_height - 20  # Empezar desde arriba

    # FUNCIÓN PARA DIBUJAR LÍNEA
    def draw_line(y):
        p.line(margin_left, y, margin_right, y)

    # FUNCIÓN PARA TEXTO CENTRADO
    def draw_centered_text(text, y, font_size=10, bold=False):
        if bold:
            p.setFont("Helvetica-Bold", font_size)
        else:
            p.setFont("Helvetica", font_size)
        text_width = p.stringWidth(text, "Helvetica", font_size)
        x = (ticket_width - text_width) / 2
        p.drawString(x, y, text)

    # FUNCIÓN PARA TEXTO CON COLUMNAS
    def draw_columns(left_text, right_text, y, font_size=10):
        p.setFont("Helvetica", font_size)
        p.drawString(margin_left, y, left_text)
        right_width = p.stringWidth(right_text, "Helvetica", font_size)
        p.drawString(margin_right - right_width, y, right_text)

    # ENCABEZADO
    draw_centered_text(pedido.restaurante.nombre_local, current_y, 12, True)
    current_y -= 15
    
    draw_centered_text(f"Pedido #{pedido.numero_pedido}", current_y, 10, True)
    current_y -= 12
    
    draw_centered_text(pedido.fecha.strftime('%d/%m/%Y %H:%M'), current_y, 8)
    current_y -= 15
    
    draw_line(current_y)
    current_y -= 10

    # INFORMACIÓN DEL CLIENTE
    p.setFont("Helvetica-Bold", 9)
    p.drawString(margin_left, current_y, "CLIENTE:")
    current_y -= 12
    
    p.setFont("Helvetica", 8)
    p.drawString(margin_left, current_y, pedido.cliente)
    current_y -= 10
    
    p.drawString(margin_left, current_y, f"Tel: {pedido.telefono}")
    current_y -= 10
    
    if pedido.direccion and pedido.direccion != 'Retiro en local':
        p.drawString(margin_left, current_y, f"Dir: {pedido.direccion}")
        current_y -= 10
    
    if pedido.tipo_pedido:
        tipo = "DELIVERY" if pedido.tipo_pedido == 'delivery' else "RETIRO"
        p.drawString(margin_left, current_y, f"Tipo: {tipo}")
        current_y -= 10
    
    if pedido.aclaraciones:
        p.drawString(margin_left, current_y, f"Aclaraciones: {pedido.aclaraciones}")
        current_y -= 15
    
    draw_line(current_y)
    current_y -= 10

    # PRODUCTOS
    draw_centered_text("PRODUCTOS", current_y, 10, True)
    current_y -= 12
    
    subtotal = Decimal('0.00')
    for item in pedido.items.all():
        # Nombre del producto y cantidad
        p.setFont("Helvetica-Bold", 8)
        product_text = f"{item.nombre_producto} x{item.cantidad}"
        p.drawString(margin_left, current_y, product_text)
        current_y -= 8
        
        # Precio unitario y subtotal
        p.setFont("Helvetica", 7)
        price_text = f"${item.precio_unitario} c/u = ${item.subtotal}"
        p.drawString(margin_left, current_y, price_text)
        current_y -= 8
        
        # Opciones seleccionadas
        if item.opciones_seleccionadas:
            for opcion in item.opciones_seleccionadas:
                opcion_text = f"  + {opcion['nombre']}"
                if Decimal(opcion['precio_adicional']) > 0:
                    opcion_text += f" (+${opcion['precio_adicional']})"
                p.drawString(margin_left, current_y, opcion_text)
                current_y -= 6
        
        subtotal += item.subtotal
        current_y -= 4  # Espacio entre productos
    
    draw_line(current_y)
    current_y -= 8

    # RESUMEN DE PAGOS
    draw_centered_text("RESUMEN", current_y, 9, True)
    current_y -= 10
    
    # Subtotal
    draw_columns("Subtotal:", f"${subtotal:.2f}", current_y, 8)
    current_y -= 8
    
    # Descuento en efectivo
    if pedido.cash_discount_applied and pedido.cash_discount_percentage > 0:
        desc_text = f"Desc. efectivo ({pedido.cash_discount_percentage}%):"
        draw_columns(desc_text, f"-${pedido.monto_descuento_efectivo:.2f}", current_y, 8)
        current_y -= 8
    
    # Descuento por código
    if pedido.codigo_descuento and pedido.monto_descuento_codigo:
        desc_text = f"Desc. {pedido.codigo_descuento}:"
        draw_columns(desc_text, f"-${pedido.monto_descuento_codigo:.2f}", current_y, 8)
        current_y -= 8
    
    # Costo de envío
    if pedido.costo_envio and pedido.costo_envio > 0:
        draw_columns("Envío:", f"${pedido.costo_envio:.2f}", current_y, 8)
        current_y -= 8
    
    # Línea antes del total
    draw_line(current_y)
    current_y -= 8
    
    # TOTAL
    draw_columns("TOTAL:", f"${pedido.total:.2f}", current_y, 10)
    current_y -= 12
    
    draw_line(current_y)
    current_y -= 10

    # INFORMACIÓN ADICIONAL
    # Método de pago
    metodo_pago = "EFECTIVO" if pedido.metodo_pago == 'efectivo' else "MERCADO PAGO"
    draw_columns("Método pago:", metodo_pago, current_y, 8)
    current_y -= 8
    
    # Estado del pedido
    estado_map = {
        'pendiente': 'PENDIENTE',
        'en_preparacion': 'EN PREPARACIÓN',
        'listo': 'LISTO',
        'en_entrega': 'EN ENTREGA',
        'entregado': 'ENTREGADO',
        'cancelado': 'CANCELADO'
    }
    estado = estado_map.get(pedido.estado, pedido.estado.upper())
    draw_columns("Estado:", estado, current_y, 8)
    current_y -= 8
    
    # Tiempo estimado si existe
    if pedido.tiempo_estimado:
        tiempo_map = {
            '15-30': '15-30 min',
            '30-40': '30-40 min', 
            '45-60': '45-60 min',
            '60-90': '60-90 min'
        }
        tiempo = tiempo_map.get(pedido.tiempo_estimado, pedido.tiempo_estimado)
        draw_columns("Tiempo estimado:", tiempo, current_y, 8)
        current_y -= 8

    # ESPACIO FINAL
    current_y -= 15
    draw_centered_text("¡Gracias por su pedido!", current_y, 9)
    current_y -= 8
    draw_centered_text("Vuelva pronto!", current_y, 8)

    p.showPage()
    p.save()
    return response

@login_required
@never_cache
@no_cache_view
def configuracion_horarios(request):
    restaurante = get_object_or_404(Restaurante, id=request.user.id)

    if request.method == 'POST':
        demora_form = RestauranteDemoraForm(request.POST, instance=restaurante)
        formset = HorarioRestauranteFormSet(request.POST, instance=restaurante, prefix='horarios')

        if demora_form.is_valid() and formset.is_valid():
            demora_form.save()
            formset.save()
            return redirect('configuracion_horarios')
        # No agregar mensajes de error aquí
    else:
        demora_form = RestauranteDemoraForm(instance=restaurante)
        formset = HorarioRestauranteFormSet(instance=restaurante, prefix='horarios')
        for form in formset:
            dia_semana = form.initial.get('dia_semana') if form.initial else form['dia_semana'].value()
            hora_apertura = form.initial.get('hora_apertura') if form.initial else form['hora_apertura'].value()
            hora_cierre = form.initial.get('hora_cierre') if form.initial else form['hora_cierre'].value()
            print(f"Form data: dia_semana={dia_semana}, hora_apertura={hora_apertura}, hora_cierre={hora_cierre}")

    horarios = HorarioRestaurante.objects.filter(restaurante=restaurante).order_by('dia_semana', 'hora_apertura')
    horarios_por_dia = {dia: [] for dia, _ in HorarioRestaurante.DIA_SEMANA_CHOICES}
    for horario in horarios:
        horarios_por_dia[horario.dia_semana].append(horario)

    horas = [hour for hour, _ in HOUR_CHOICES]
    minutos = [minute for minute, _ in MINUTE_CHOICES]

    return render(request, 'core/configuracion_horarios.html', {
        'demora_form': demora_form,
        'formset': formset,
        'restaurante': restaurante,
        'dias_semana': HorarioRestaurante.DIA_SEMANA_CHOICES,
        'horarios_por_dia': horarios_por_dia,
        'horas': horas,
        'minutos': minutos,
    })

@login_required
@never_cache
@no_cache_view
def toggle_cerrado_manualmente(request):
    if request.method == 'POST':
        try:
            restaurante = get_object_or_404(Restaurante, id=request.user.id)
            estado_control = request.POST.get('estado_control')  # Recibimos 'cerrado', 'automatico' o 'abierto'
            if estado_control not in ['cerrado', 'automatico', 'abierto']:
                return JsonResponse({'success': False, 'error': 'Estado inválido'}, status=400)
            print(f"Actualizando estado_control para {restaurante.username} a {estado_control}")  # Depuración
            restaurante.estado_control = estado_control
            restaurante.save()
            print(f"Estado actualizado: estado_control = {restaurante.estado_control}")  # Depuración
            return JsonResponse({
                'success': True,
                'estado_control': estado_control,
                'esta_abierto': restaurante.esta_abierto()  # Devolvemos el estado actualizado
            })
        except Exception as e:
            print(f"Error al actualizar el estado: {str(e)}")  # Depuración
            return JsonResponse({'success': False, 'error': str(e)}, status=500)
    return JsonResponse({'success': False, 'error': 'Método no permitido'}, status=400)

# views.py
@login_required
@never_cache
@no_cache_view
def guardar_horarios_dia(request):
    if request.method == 'POST':
        restaurante = get_object_or_404(Restaurante, id=request.user.id)
        dia = request.POST.get('dia')
        horarios_data = json.loads(request.POST.get('horarios', '[]'))

        print(f"Guardando horarios para el día {dia}: {horarios_data}")

        # Eliminar horarios existentes para este día
        HorarioRestaurante.objects.filter(restaurante=restaurante, dia_semana=dia).delete()

        # Crear nuevos horarios
        horarios_list = []
        for horario in horarios_data:
            hora_apertura = horario['hora_apertura']
            hora_cierre = horario['hora_cierre']
            if len(hora_apertura.split(':')) == 2:
                hora_apertura = f"{hora_apertura}:00"
            if len(hora_cierre.split(':')) == 2:
                hora_cierre = f"{hora_cierre}:00"

            # Validate that closing time is after opening time
            apertura_parts = hora_apertura.split(':')
            cierre_parts = hora_cierre.split(':')
            apertura_h = int(apertura_parts[0])
            apertura_m = int(apertura_parts[1])
            cierre_h = int(cierre_parts[0])
            cierre_m = int(cierre_parts[1])

            if apertura_h > cierre_h or (apertura_h == cierre_h and apertura_m >= cierre_m):
                return JsonResponse({
                    'success': False,
                    'error': f'La hora de cierre ({hora_cierre}) debe ser posterior a la hora de apertura ({hora_apertura})'
                }, status=400)

            print(f"Creando horario: {hora_apertura} - {hora_cierre}")

            horario_obj = HorarioRestaurante.objects.create(
                restaurante=restaurante,
                dia_semana=int(dia),
                hora_apertura=hora_apertura,
                hora_cierre=hora_cierre
            )

            horarios_list.append({
                'id': horario_obj.id,
                'hora_apertura': str(horario_obj.hora_apertura),
                'hora_cierre': str(horario_obj.hora_cierre)
            })

        print(f"Horarios guardados: {horarios_list}")

        return JsonResponse({
            'success': True,
            'message': f'Horarios para el día {dia} guardados correctamente.',
            'horarios': horarios_list
        })
    return JsonResponse({'success': False, 'error': 'Método no permitido'}, status=400)

@login_required
@never_cache
@no_cache_view
def guardar_demora(request):
    if request.method == 'POST':
        restaurante = get_object_or_404(Restaurante, id=request.user.id)
        demora_form = RestauranteDemoraForm(request.POST, instance=restaurante)
        if demora_form.is_valid():
            demora_form.save()
            return JsonResponse({
                'success': True,
                'message': 'Configuración de demora guardada correctamente.',
                'tiene_demora': restaurante.tiene_demora,
                'tiempo_demora': restaurante.tiempo_demora
            })
        return JsonResponse({'success': False, 'error': demora_form.errors}, status=400)
    return JsonResponse({'success': False, 'error': 'Método no permitido'}, status=400)

@never_cache
@no_cache_view
def obtener_estado_restaurante(request, username):
    restaurante = get_object_or_404(Restaurante, username=username)
    horarios = HorarioRestaurante.objects.filter(restaurante=restaurante)
    horarios_por_dia = {}
    for dia, dia_nombre in HorarioRestaurante.DIA_SEMANA_CHOICES:
        horarios_dia = horarios.filter(dia_semana=dia)
        horarios_list = [
            {
                'hora_apertura': str(horario.hora_apertura),
                'hora_cierre': str(horario.hora_cierre)
            }
            for horario in horarios_dia
        ]
        horarios_por_dia[dia] = horarios_list

    return JsonResponse({
        'success': True,
        'esta_abierto': restaurante.esta_abierto(),
        'estado_control': restaurante.estado_control,
        'horarios': horarios_por_dia,
        'tiene_demora': restaurante.tiene_demora,
        'tiempo_demora': restaurante.tiempo_demora
    })




@login_required
@never_cache
@no_cache_view
def configuraciones(request):
    restaurante = get_object_or_404(Restaurante, id=request.user.id)
    config_form = ConfigRestauranteForm(instance=restaurante)
    descuento_form = CodigoDescuentoForm()
    restaurant_qr = generate_qr_for_restaurant(restaurante.nombre_local)
    return render(request, 'core/configuraciones.html', {
        'config_form': config_form,
        'descuento_form': descuento_form,
        'restaurante': restaurante,
        'restaurant_qr': restaurant_qr,
    })

@login_required
@never_cache
@no_cache_view
def configurar_restaurante(request):
    restaurante = get_object_or_404(Restaurante, id=request.user.id)
    if request.method == 'POST':
        form = ConfigRestauranteForm(request.POST, request.FILES, instance=restaurante)
        if form.is_valid():
            old_nombre_local = restaurante.nombre_local
            try:
                form.save()
                if old_nombre_local != form.instance.nombre_local:
                    RestaurantQR.objects.filter(name=old_nombre_local).delete()
                    generate_qr_for_restaurant(form.instance.nombre_local)
                messages.success(request, 'Configuración actualizada correctamente.')
                return redirect('configuraciones')
            except ValidationError as e:
                for field, errors in e.error_dict.items():
                    for error in errors:
                        messages.error(request, f"Error en {field}: {error}")
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"Error en {field}: {error}")
    else:
        form = ConfigRestauranteForm(instance=restaurante)
    restaurant_qr = generate_qr_for_restaurant(restaurante.nombre_local)
    return render(request, 'core/configuraciones.html', {
        'config_form': form,
        'descuento_form': CodigoDescuentoForm(),
        'restaurante': restaurante,
        'restaurant_qr': restaurant_qr,
    })

@login_required
@require_POST
@never_cache
@no_cache_view
def actualizar_metodos_pago(request):
    restaurante = get_object_or_404(Restaurante, id=request.user.id)
    
    try:
        restaurante.metodo_pago_mercadopago = request.POST.get('metodo_pago_mercadopago') == 'on'
        restaurante.metodo_pago_alias = request.POST.get('metodo_pago_alias') == 'on'
        restaurante.alias_cbu = request.POST.get('alias_cbu', '').strip()
        
        # === NUEVA VALIDACIÓN: Exclusividad entre métodos de pago ===
        if restaurante.metodo_pago_mercadopago and restaurante.metodo_pago_alias:
            messages.error(request, 'No puedes tener ambos métodos de pago activados al mismo tiempo. Solo puedes habilitar uno.')
            return redirect('configuraciones')
        
        # Validar que al menos un método esté habilitado
        if not restaurante.metodo_pago_mercadopago and not restaurante.metodo_pago_alias:
            messages.error(request, 'Debes habilitar al menos un método de pago.')
            return redirect('configuraciones')
        
        # Validar que si alias está habilitado, tenga un valor
        if restaurante.metodo_pago_alias and not restaurante.alias_cbu:
            messages.error(request, 'Debes ingresar un alias o CBU si habilitas el pago por transferencia.')
            return redirect('configuraciones')
        
        restaurante.save()
        messages.success(request, 'Configuración de métodos de pago actualizada correctamente.')
        
    except Exception as e:
        logger.error(f"Error al actualizar métodos de pago: {str(e)}")
        messages.error(request, 'Error al actualizar la configuración de pagos.')
    
    return redirect('configuraciones')

@login_required
@never_cache
@no_cache_view
def agregar_codigo_descuento(request):
    """Vista para añadir un nuevo código de descuento vía AJAX."""
    if request.method == 'POST':
        form = CodigoDescuentoForm(request.POST)
        if form.is_valid():
            restaurante = get_object_or_404(Restaurante, id=request.user.id)
            codigo = {
                'nombre': form.cleaned_data['nombre_codigo'].upper(),
                'porcentaje': int(form.cleaned_data['porcentaje'])
            }
            # Aseguramos que codigos_descuento sea una lista
            if not isinstance(restaurante.codigos_descuento, list):
                restaurante.codigos_descuento = []
            # Verificamos si el código ya existe
            if any(c['nombre'] == codigo['nombre'] for c in restaurante.codigos_descuento):
                return JsonResponse({'success': False, 'error': 'El código ya existe.'}, status=400)
            restaurante.codigos_descuento.append(codigo)
            restaurante.save()
            return JsonResponse({'success': True, 'codigo': codigo})
        return JsonResponse({'success': False, 'error': form.errors}, status=400)
    return JsonResponse({'success': False, 'error': 'Método no permitido'}, status=405)

@login_required
@never_cache
@no_cache_view
def eliminar_codigo_descuento(request):
    """Vista para eliminar un código de descuento vía AJAX."""
    if request.method == 'POST':
        restaurante = get_object_or_404(Restaurante, id=request.user.id)
        nombre_codigo = request.POST.get('nombre_codigo')
        if not nombre_codigo:
            return JsonResponse({'success': False, 'error': 'Nombre de código requerido.'}, status=400)
        # Filtramos el código a eliminar
        codigos = [c for c in restaurante.codigos_descuento if c['nombre'] != nombre_codigo]
        if len(codigos) == len(restaurante.codigos_descuento):
            return JsonResponse({'success': False, 'error': 'Código no encontrado.'}, status=404)
        restaurante.codigos_descuento = codigos
        restaurante.save()
        return JsonResponse({'success': True})
    return JsonResponse({'success': False, 'error': 'Método no permitido'}, status=405)

@login_required
@require_POST
@never_cache
@no_cache_view
def aplicar_descuento_producto(request, producto_id):
    try:
        # Check if request body is empty or not valid JSON
        if not request.body:
            logger.warning(f"Empty request body for product {producto_id}")
            return JsonResponse({'success': False, 'error': 'No se proporcionaron datos.'}, status=400)

        try:
            data = json.loads(request.body)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in aplicar_descuento_producto for product {producto_id}: {str(e)}")
            return JsonResponse({'success': False, 'error': 'Formato JSON inválido.'}, status=400)

        producto = get_object_or_404(Producto, id=producto_id, restaurante=request.user)
        discount_percentage = int(data.get('discount_percentage', 0))

        if discount_percentage < 0 or discount_percentage > 90:
            logger.warning(f"Invalid discount percentage for product {producto.id}: {discount_percentage}")
            return JsonResponse({'success': False, 'error': 'El porcentaje de descuento debe estar entre 0% y 90%.'}, status=400)

        with transaction.atomic():
            if discount_percentage > 0:
                if not producto.precio_original:
                    producto.precio_original = producto.precio
                original_price = producto.precio_original
                descuento = original_price * (Decimal(discount_percentage) / Decimal(100))
                producto.precio = (original_price - descuento).quantize(Decimal('0.01'))
                producto.tiene_descuento = True
            else:
                producto.precio = (producto.precio_original or producto.precio).quantize(Decimal('0.01'))
                producto.precio_original = None
                producto.tiene_descuento = False

            try:
                producto.full_clean()
                producto.save()
            except ValidationError as e:
                logger.error(f"Validation error for product ID {producto.id}: {e}")
                return JsonResponse({'success': False, 'error': str(e)}, status=400)

            opciones_actualizadas = []
            for opcion_categoria in producto.opcion_categorias.all():
                categoria_data = {
                    'nombre': opcion_categoria.nombre,
                    'max_selecciones': opcion_categoria.max_selecciones,
                    'opciones': []
                }
                for opcion in opcion_categoria.opciones.all():
                    if opcion.tiene_descuento:
                        opcion.aplicar_descuento(discount_percentage)
                        try:
                            opcion.full_clean()
                            opcion.save()
                        except ValidationError as e:
                            logger.error(f"Validation error for OpcionProducto ID {opcion.id}: {e}")
                            continue
                    categoria_data['opciones'].append({
                        'nombre': opcion.nombre,
                        'precio_adicional': str(opcion.precio_adicional),
                        'precio_adicional_original': str(opcion.precio_adicional_original) if opcion.precio_adicional_original else None,
                        'tiene_descuento': opcion.tiene_descuento,
                        'agotado': opcion.agotado
                    })
                opciones_actualizadas.append(categoria_data)

        logger.info(f"Discount applied to product ID {producto.id}: {discount_percentage}%")
        return JsonResponse({
            'success': True,
            'nuevo_precio': str(producto.precio),
            'precio_original': str(producto.precio_original) if producto.precio_original else None,
            'tiene_descuento': producto.tiene_descuento,
            'discount_percentage': producto.discount_percentage,
            'opciones_actualizadas': opciones_actualizadas
        })
    except (ValueError, TypeError, InvalidOperation) as e:
        logger.error(f"Invalid input in aplicar_descuento_producto: {str(e)}")
        return JsonResponse({'success': False, 'error': f'Entrada inválida: {str(e)}'}, status=400)
    except Exception as e:
        logger.error(f"Unexpected error in aplicar_descuento_producto: {str(e)}")
        return JsonResponse({'success': False, 'error': f'Error inesperado: {str(e)}'}, status=500)



@login_required
@require_POST
@never_cache
@no_cache_view
def update_cash_discount(request):
    restaurante = get_object_or_404(Restaurante, id=request.user.id)
    try:
        cash_discount_enabled = request.POST.get('enabled') == 'true'
        cash_discount_percentage = int(request.POST.get('percentage', 0))

        if not (0 <= cash_discount_percentage <= 50):
            return JsonResponse({
                'success': False,
                'error': 'El porcentaje debe estar entre 0% y 50%.'
            }, status=400)

        restaurante.cash_discount_enabled = cash_discount_enabled
        restaurante.cash_discount_percentage = cash_discount_percentage
        restaurante.save()

        return JsonResponse({
            'success': True,
            'enabled': cash_discount_enabled,
            'percentage': cash_discount_percentage
        })
    except ValueError:
        return JsonResponse({
            'success': False,
            'error': 'Porcentaje inválido.'
        }, status=400)    

@cache_page(3600)  # Cache server-side for 1 hour
def home(request):
    restaurantes_activos = Restaurante.objects.filter(activo=True)
    response = render(request, 'core/home.html', {
        'restaurantes': restaurantes_activos
    })
    response['Cache-Control'] = 'max-age=3600, must-revalidate'
    return response

@never_cache
@no_cache_view
def csrf_failure(request, reason=""):
    """
    Custom CSRF failure view to handle AJAX and non-AJAX requests.
    Returns JSON for AJAX requests and renders a template for others.
    """
    logger.warning(f"CSRF failure for request {request.path}: {reason}")

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'success': False,
            'error': 'CSRF verification failed. Please refresh the page and try again.'
        }, status=403)

    return render(request, 'core/csrf_failure.html', {
        'reason': reason,
        'mensaje': 'CSRF verification failed. Please refresh the page.'
    }, status=403)

def generate_qr_for_restaurant(restaurant_name):
    restaurant_qr, created = RestaurantQR.objects.get_or_create(name=restaurant_name)

    # Generar el slug a partir de restaurant_name
    slug = restaurant_name.replace(' ', '').lower()
    qr_url = f"https://piattoweb.com/{slug}"

    # Crear el código QR
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=4,
    )
    qr.add_data(qr_url)
    qr.make(fit=True)

    # Generar la imagen QR
    qr_image = qr.make_image(fill_color="black", back_color="white")
    qr_image_io = io.BytesIO()
    qr_image.save(qr_image_io, format='PNG')
    qr_image_io.seek(0)

    # Guardar en S3
    filename = f"{slug}_qr.png"
    restaurant_qr.qr_image.save(filename, ContentFile(qr_image_io.getvalue()), save=True)
    restaurant_qr.url = qr_url
    restaurant_qr.save()

    print(f"QR image saved to S3: s3://piatto-media-2025/media/qrcodes/{filename}")
    return restaurant_qr

@api_view(['GET', 'POST'])
@csrf_exempt
@never_cache
def hello(request):
    # === SECURITY FIX: VALIDATE TOKEN FIRST ===
    token = None
    payment_id = None
    status = None

    # Get parameters according to method
    if request.method == 'POST':
        # Manejar diferentes formatos de webhook de Mercado Pago
        if request.content_type == 'application/json':
            try:
                data = json.loads(request.body)
                # Para webhooks de payment
                if 'data' in data and 'id' in data.get('data', {}):
                    payment_id = data['data']['id']
                else:
                    payment_id = data.get('id')
                
                token = data.get('external_reference')
                status = data.get('status')
                
                # Verificar si es una notificación de merchant_order (que no tiene los datos que necesitamos)
                topic = data.get('topic')
                if topic == 'merchant_order':
                    logger.debug("Merchant order notification received (ignoring)")
                    return JsonResponse({'status': 'ignored', 'message': 'Merchant order notification'}, status=200)
                    
            except json.JSONDecodeError:
                # Si falla el JSON, intentar con query params o form data
                token = request.POST.get("external_reference") or request.GET.get("external_reference")
                payment_id = request.POST.get("payment_id") or request.GET.get("payment_id") or request.GET.get("data.id")
                status = request.POST.get("status") or request.GET.get("status")
        else:
            # Para POST con form data
            token = request.POST.get("external_reference") or request.GET.get("external_reference")
            payment_id = request.POST.get("payment_id") or request.GET.get("payment_id") or request.GET.get("data.id")
            status = request.POST.get("status") or request.GET.get("status")
    else:
        # Para GET (redirecciones del usuario)
        token = request.GET.get("external_reference")
        payment_id = request.GET.get("payment_id")
        status = request.GET.get("status")

    # === CRITICAL SECURITY VALIDATION ===
    # 1. Always require token
    if not token:
        logger.warning("No token provided in request")
        if request.method == 'POST':
            return JsonResponse({'status': 'error', 'message': 'Missing order token'}, status=400)
        return redirect('home')

    # 2. Validate token exists and get order EARLY
    try:
        pedido = Pedido.objects.get(token=token)
    except Pedido.DoesNotExist:
        logger.warning(f"Invalid token attempted: {token} from IP: {request.META.get('REMOTE_ADDR')}")
        if request.method == 'POST':
            return JsonResponse({'status': 'error', 'message': 'Order not found'}, status=404)
        return redirect('home')

    # 3. For POST requests (real webhooks), require payment_id
    if request.method == 'POST' and not payment_id:
        logger.warning(f"Webhook POST without payment_id for token: {token}")
        return JsonResponse({'status': 'error', 'message': 'Missing payment ID'}, status=400)

    # Log solo si tenemos al menos algún dato útil
    if token or payment_id or status:
        logger.info(f"Webhook called with token={token}, payment_id={payment_id}, status={status}")
    else:
        logger.debug("Webhook received without relevant data")
        if request.method == 'POST':
            return JsonResponse({'status': 'ignored', 'message': 'No relevant data'}, status=200)
        return redirect('home')

    try:
        # This check is now redundant but keeping for safety
        if not payment_id or not token:
            logger.warning("Webhook received without payment_id or token")
            if request.method == 'POST':
                return JsonResponse({'status': 'ignored', 'message': 'Incomplete webhook data'}, status=200)
            return redirect('home')

        # pedido is already loaded from security validation above

        if not pedido.payment_id:
            pedido.payment_id = payment_id
            pedido.save()
        elif pedido.payment_id != payment_id:
            logger.error(f"Payment ID mismatch: {pedido.payment_id} != {payment_id}")
            if request.method == 'POST':
                return JsonResponse({'status': 'error', 'message': 'Payment ID mismatch'}, status=400)
            return redirect('home')

        # For GET requests (user redirects), we can proceed without Mercado Pago API call
        # since the user is just being redirected to confirmation page
        if request.method == 'GET' and not payment_id:
            # User redirect without payment_id - just show confirmation page
            redirect_url = reverse('confirmacion_pedido', args=[pedido.restaurante.username, str(pedido.token)])
            if status:
                redirect_url += f"?status={status}&external_reference={token}"
            logger.info(f"Redirecting user to confirmation: {redirect_url}")
            return redirect(redirect_url)

        # Only call Mercado Pago API if we have payment_id
        access_token = get_mp_access_token(pedido.restaurante)
        headers = {'Authorization': f'Bearer {access_token}'}
        ml_response = requests.get(f'https://api.mercadopago.com/v1/payments/{payment_id}', headers=headers)
        if not ml_response.ok:
            logger.error(f"Mercado Pago API error: Status {ml_response.status_code}, Response: {ml_response.text}")
            if request.method == 'POST':
                return JsonResponse({'status': 'error', 'message': 'Mercado Pago API error'}, status=500)
            return redirect('home')

        try:
            data = ml_response.json()
        except ValueError:
            logger.error(f"Invalid JSON response from Mercado Pago: {ml_response.text}")
            if request.method == 'POST':
                return JsonResponse({'status': 'error', 'message': 'Invalid JSON response'}, status=500)
            return redirect('home')

        status = data.get('status', None)
        if not status:
            logger.error(f"No status in Mercado Pago response: {data}")
            if request.method == 'POST':
                return JsonResponse({'status': 'error', 'message': 'No status in response'}, status=500)
            return redirect('home')

        if pedido.estado != 'procesando_pago':
            logger.warning(f"Pedido {pedido.id} not in procesando_pago state: {pedido.estado}")
            if request.method == 'POST':
                return JsonResponse({'status': 'warning', 'message': 'Order not in processing state'})
            return redirect('home')

        if status == "approved":
            pedido.estado = 'pendiente'
            pedido.save()
            # Actualizar cache para SSE
            print(f"⚡ Webhook: Pago APROBADO para pedido #{pedido.numero_pedido}, ACTUALIZACIÓN INMEDIATA...")
            actualizar_cache_pedidos(pedido.restaurante.id)
            
        elif status in ('pending', 'in_process'):
            pedido.estado = 'procesando_pago'
            pedido.save()
            # Actualizar cache para SSE
            print(f"⚡ Webhook: Pago PENDIENTE para pedido #{pedido.numero_pedido}, ACTUALIZACIÓN INMEDIATA...")
            actualizar_cache_pedidos(pedido.restaurante.id)
            
        elif status in ("cancelled", "rejected"):
            pedido.estado = 'error_pago'
            pedido.motivo_error_pago = "No se pudo procesar el pago"
            pedido.fecha_error_pago = timezone.now()
            pedido.save()
            # Actualizar cache para SSE
            print(f"⚡ Webhook: Pago RECHAZADO para pedido #{pedido.numero_pedido}, ACTUALIZACIÓN INMEDIATA...")
            actualizar_cache_pedidos(pedido.restaurante.id)

        # Para webhooks POST, retornar JSON en lugar de redirect
        if request.method == 'POST':
            return JsonResponse({
                'status': 'success', 
                'message': 'Webhook processed successfully',
                'order_id': pedido.id,
                'order_status': pedido.estado
            })

        # Para GET (redirecciones de usuario), hacer redirect
        redirect_url = reverse('confirmacion_pedido', args=[pedido.restaurante.username, str(pedido.token)])
        redirect_url += f"?status={status}&external_reference={token}"
        logger.info(f"Redirecting to: {redirect_url}")
        return redirect(redirect_url)

    except ValueError as ve:
        logger.error(f"Error de token en hello: {str(ve)}")
        if request.method == 'POST':
            return JsonResponse({'status': 'error', 'message': 'No se pudo procesar: cuenta de Mercado Pago no vinculada o token inválido.'}, status=400)
        return redirect('home')
    except Exception as e:
        logger.error(f"Error in hello view: {str(e)}", exc_info=True)
        if request.method == 'POST':
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
        return redirect('home')