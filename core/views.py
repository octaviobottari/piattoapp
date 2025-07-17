from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.db.models import Prefetch, F, Sum, Count
from django.views.decorators.http import require_POST
from django.http import JsonResponse, HttpResponse
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.forms.models import modelformset_factory  # Use modelformset_factory
from datetime import datetime, timedelta
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
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.forms import formset_factory, inlineformset_factory
from django.views.decorators.csrf import csrf_protect
import json
from decimal import Decimal, InvalidOperation
import decimal
import logging
import calendar
import qrcode
import os
from django.conf import settings
import io
from django.core.files import File
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage  # Importar default_storage
from botocore.exceptions import ClientError  # Importar ClientError
from rest_framework.decorators import api_view
from rest_framework.response import Response 

logger = logging.getLogger(__name__)


def error_view(request, exception=None):
    from django.contrib.auth.decorators import login_required
    from django.http import HttpResponse
    from django.shortcuts import render
    import logging

    logger = logging.getLogger(__name__)

    # Log the error for debugging
    logger.error(f"Unexpected error occurred: {str(exception)}", exc_info=True)

    # Determine the redirect URL based on user authentication
    if request.user.is_authenticated:
        redirect_url = reverse('panel')
        context = {
            'message': 'Ha ocurrido un error inesperado. Por favor, contacte al soporte si el problema persiste.',
            'redirect_url': redirect_url,
            'redirect_text': 'Volver al Panel'
        }
    else:
        redirect_url = reverse('home')
        context = {
            'message': 'Ha ocurrido un error inesperado. Por favor, intente de nuevo o contacte al soporte si el problema continúa.',
            'redirect_url': redirect_url,
            'redirect_text': 'Volver a la Página Principal'
        }

    # Render a custom error template
    return render(request, 'core/error.html', context, status=500)

# Redirect registro to login
def registro_view(request):
    return redirect('login')

def login_view(request):
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
def panel_view(request):
    pedidos_recientes = Pedido.objects.filter(
        restaurante=request.user
    ).order_by('-fecha')[:5]
    
    return render(request, 'core/panel.html', {
        'pedidos_recientes': pedidos_recientes
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
def eliminar_producto(request, producto_id):
    producto = get_object_or_404(Producto, id=producto_id, restaurante=request.user)
    producto.delete()
    messages.success(request, 'Producto eliminado correctamente.')
    return redirect('mi_menu')

@require_POST
@login_required
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
def eliminar_categoria(request, categoria_id):
    categoria = get_object_or_404(Categoria, id=categoria_id, restaurante=request.user)
    Producto.objects.filter(categoria=categoria).update(categoria=None)
    categoria.delete()
    messages.success(request, 'Categoría eliminada correctamente.')
    return redirect('mi_menu')

@login_required
@require_POST
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

@login_required
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
def pedidos_pendientes_html(request):
    pedidos_pendientes = Pedido.objects.filter(
        restaurante=request.user,
        estado='pendiente'
    ).order_by('-fecha')
    return render(request, 'core/pedidos_columnas.html', {
        'pedidos_pendientes': pedidos_pendientes,
        'pendientes_only': True,
        'tiempos_estimados': Pedido.TIEMPO_ESTIMADO_CHOICES,
        'motivos_cancelacion': Pedido.MOTIVO_CANCELACION_CHOICES
    })

@login_required
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
@require_POST
def eliminar_pedido(request, pedido_id):
    pedido = get_object_or_404(Pedido, id=pedido_id, restaurante=request.user)
    if pedido.estado != 'cancelado':
        return JsonResponse({'success': False, 'error': 'El pedido no está cancelado'})
    
    pedido.delete()
    return JsonResponse({'success': True})

@login_required
@require_POST
def marcar_en_entrega(request, pedido_id):
    pedido = get_object_or_404(Pedido, id=pedido_id, restaurante=request.user)
    if pedido.estado != 'listo':
        return JsonResponse({'success': False, 'error': 'El pedido no está listo para entrega'})
    
    pedido.estado = 'en_entrega'
    pedido.fecha_en_entrega = timezone.now()
    pedido.save()
    return JsonResponse({'success': True})

@login_required
@require_POST
def archivar_pedido(request, pedido_id):
    pedido = get_object_or_404(Pedido, id=pedido_id, restaurante=request.user)
    if pedido.estado not in ['listo', 'en_entrega']:
        return JsonResponse({'success': False, 'error': 'El pedido no puede ser archivado'})
    
    pedido.estado = 'archivado'
    pedido.save()
    return JsonResponse({'success': True})

@login_required
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

@login_required
def todos_pedidos(request):
    pedidos = Pedido.objects.filter(
        restaurante=request.user,
        estado='archivado'
    ).order_by('-fecha')
    return render(request, 'core/todos_pedidos.html', {
        'pedidos': pedidos,
        'restaurante': request.user
    })

@login_required
@require_POST
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
    return JsonResponse({'success': True})

@login_required
@require_POST
def rechazar_pedido(request, pedido_id):
    pedido = get_object_or_404(Pedido, id=pedido_id, restaurante=request.user)
    motivo = request.POST.get('motivo')
    if not motivo or motivo not in dict(Pedido.MOTIVO_CANCELACION_CHOICES):
        return JsonResponse({'success': False, 'error': 'Motivo de cancelación inválido'})
    
    pedido.estado = 'cancelado'
    pedido.motivo_cancelacion = motivo
    pedido.fecha_cancelado = timezone.now()
    pedido.save()
    return JsonResponse({'success': True})

@login_required
@require_POST
def actualizar_estado(request, pedido_id):
    pedido = get_object_or_404(Pedido, id=pedido_id, restaurante=request.user)
    estado = request.POST.get('estado')
    if estado not in ['listo']:
        return JsonResponse({'success': False, 'error': 'Estado no válido'})
    
    pedido.estado = estado
    pedido.save()
    return JsonResponse({'success': True})

@login_required
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

def restaurante_publico(request, nombre_restaurante):
    reserved_paths = ['panel', 'login', 'registro', 'logout', 'admin']
    if nombre_restaurante.lower() in reserved_paths:
        return redirect('home')

    restaurante = get_object_or_404(Restaurante, username=nombre_restaurante, activo=True)
    restaurante.refresh_from_db()
    
    if request.method == 'POST':
        return procesar_pedido(request, restaurante)
    
    categorias = Categoria.objects.filter(restaurante=restaurante).prefetch_related(
        Prefetch('producto_set', queryset=Producto.objects.filter(disponible=True).order_by('nombre'))
    )
    
    response = render(request, 'core/restaurante_publico.html', {
        'restaurante': restaurante,
        'categorias': categorias,
        'color_principal': restaurante.color_principal or '#A3E1BE',
    })
    
    response['Cache-Control'] = 'no-store, no-cache, must-revalidate, proxy-revalidate'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    return response

def procesar_pedido(request, restaurante):
    if request.method == 'POST':
        try:
            with transaction.atomic():
                restaurante = get_object_or_404(Restaurante, username=restaurante)
                if not restaurante.esta_abierto:
                    return JsonResponse({'error': 'El restaurante está cerrado.'}, status=400)

                print("Datos POST recibidos:", dict(request.POST))

                # Extract datos_cliente (handle list wrapping)
                datos_cliente_raw = request.POST.get('datos_cliente', '')
                if isinstance(datos_cliente_raw, list):
                    datos_cliente_raw = datos_cliente_raw[0]
                try:
                    datos_cliente = json.loads(datos_cliente_raw) if datos_cliente_raw else {}
                except json.JSONDecodeError:
                    return JsonResponse({'error': 'Formato de datos_cliente inválido.'}, status=400)

                # Extract fields from datos_cliente
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

                # Extract productos (handle list wrapping)
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

                # Process products
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

                # Apply cash discount
                subtotal_ajustado = subtotal
                if metodo_pago == 'efectivo' and restaurante.cash_discount_enabled and restaurante.cash_discount_percentage > 0:
                    cash_discount_porcentaje = Decimal(str(restaurante.cash_discount_percentage))
                    monto_descuento_efectivo = subtotal * (cash_discount_porcentaje / 100)
                    subtotal_ajustado -= monto_descuento_efectivo
                    monto_descuento += monto_descuento_efectivo
                    cash_discount_applied = True

                # Apply code-based discount
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

                # Calculate shipping cost
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
                    estado='pendiente',
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

                # Send WebSocket notification
                channel_layer = get_channel_layer()
                async_to_sync(channel_layer.group_send)(
                    f'pedidos_restaurante_{restaurante.id}',
                    {
                        'type': 'new_pedido',
                        'pedido_id': pedido.id,
                        'message': 'Nuevo pedido recibido!'
                    }
                )

                return JsonResponse({
                    'success': True,
                    'redirect_url': pedido.get_absolute_url()
                })
        except Exception as e:
            print(f"Error en procesar_pedido: {str(e)}")
            return JsonResponse({'error': str(e)}, status=400)
    return JsonResponse({'error': 'Método no permitido'}, status=405)


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

def confirmacion_pedido(request, nombre_restaurante, token):
    pedido = get_object_or_404(Pedido, token=token, restaurante__username=nombre_restaurante)
    return render(request, 'core/confirmacion_pedido.html', {
        'pedido': pedido,
        'restaurante': pedido.restaurante,
        'color_principal': pedido.restaurante.color_principal or '#A3E1BE'
    })

@login_required
def imprimir_ticket(request, pedido_id):
    pedido = get_object_or_404(Pedido, id=pedido_id, restaurante=request.user)
    
    # Marcar como impreso
    pedido.impreso = True
    pedido.save()
    
    # Configurar respuesta PDF
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'filename=ticket_pedido_{pedido.id}.pdf'
    
    # Crear PDF
    p = canvas.Canvas(response, pagesize=letter)
    width, height = letter
    
    # Encabezado
    p.setFont("Helvetica-Bold", 16)
    p.drawString(100, height - 50, f"Ticket Pedido #{pedido.id}")
    p.setFont("Helvetica", 12)
    p.drawString(100, height - 80, f"Restaurante: {pedido.restaurante.nombre_local}")
    p.drawString(100, height - 100, f"Fecha: {pedido.fecha.strftime('%d/%m/%Y %H:%M')}")
    
    # Información del cliente
    p.setFont("Helvetica-Bold", 14)
    p.drawString(100, height - 140, "Datos del Cliente")
    p.setFont("Helvetica", 12)
    p.drawString(100, height - 160, f"Nombre: {pedido.cliente}")
    p.drawString(100, height - 180, f"Teléfono: {pedido.telefono}")
    if pedido.direccion:
        p.drawString(100, height - 200, f"Dirección: {pedido.direccion}")
    
    # Productos
    p.setFont("Helvetica-Bold", 14)
    p.drawString(100, height - 240, "Productos:")
    y_position = height - 260
    subtotal = Decimal('0.00')
    for item in pedido.items.all():
        p.setFont("Helvetica", 12)
        p.drawString(120, y_position, f"• {item.nombre_producto} (x{item.cantidad})")
        p.drawString(100, y_position - 20, f"${item.precio_unitario} = ${item.subtotal}")
        if item.opciones_seleccionadas:
            p.drawString(120, y_position - 40, "Opciones:")
            for opcion in item.opciones_seleccionadas:
                p.drawString(140, y_position - 60, f"- {opcion['nombre']} (+${opcion['precio_adicional']})")
                y_position -= 20
        subtotal += item.subtotal
        y_position -= 60
    
    # Costos
    p.setFont("Helvetica", 12)
    p.drawString(100, y_position - 20, f"Subtotal: ${subtotal:.2f}")
    if pedido.costo_envio > 0:
        p.drawString(100, y_position - 40, f"Costo de Envío: ${pedido.costo_envio:.2f}")
        y_position -= 20
    if pedido.monto_descuento > 0:
        p.drawString(100, y_position - 40, f"Descuento ({pedido.codigo_descuento}): -${pedido.monto_descuento:.2f}")
        y_position -= 20
    p.setFont("Helvetica-Bold", 14)
    p.drawString(100, y_position - 60, f"Total: ${pedido.total:.2f}")
    
    # Estado del pedido
    p.drawString(100, y_position - 80, f"Estado: {pedido.get_estado_display()}")
    
    # Pie de página
    p.setFont("Helvetica", 10)
    p.drawString(100, 50, "¡Gracias por su pedido!")
    
    p.showPage()
    p.save()
    return response

# views.py
@login_required
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
def configurar_restaurante(request):
    restaurante = get_object_or_404(Restaurante, id=request.user.id)
    if request.method == 'POST':
        form = ConfigRestauranteForm(request.POST, request.FILES, instance=restaurante)
        if form.is_valid():
            # Save form and regenerate QR if nombre_local changed
            old_nombre_local = restaurante.nombre_local
            form.save()
            if old_nombre_local != form.instance.nombre_local:
                # Delete old QR and generate new one
                RestaurantQR.objects.filter(name=old_nombre_local).delete()
                generate_qr_for_restaurant(form.instance.nombre_local)
            messages.success(request, 'Configuración actualizada correctamente.')
            return redirect('configuraciones')
        else:
            messages.error(request, 'Error al guardar la configuración. Verifica los datos.')
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


def home(request): 
    restaurantes_activos = Restaurante.objects.filter(activo=True)
    return render(request, 'core/home.html', {
        'restaurantes': restaurantes_activos
    })

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

@api_view(['GET'])
def hello(request):
    data = {
        'name': "Juan",
        'message': f"Hello Juan, your first API endpoint has been created successfully!"
    }
    return Response(data)
