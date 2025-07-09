from django.contrib.auth.models import AbstractUser
from django.db import models
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
from django.db.models import JSONField
from django.urls import reverse
from decimal import Decimal
import uuid
import os
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
import qrcode

def get_restaurante_media_path(instance, filename):
    if isinstance(instance, Restaurante):
        restaurante_username = instance.username
    else:
        restaurante_username = instance.restaurante.username
    tipo = instance._meta.model_name
    if tipo == 'categoria':
        tipo = 'categorias_banners'
    elif tipo == 'producto':
        tipo = 'productos'
    elif tipo == 'restaurante':
        tipo = 'logos'
    return f'{restaurante_username}/{tipo}/{filename}'

class Restaurante(AbstractUser):
    ESTADO_CONTROL_CHOICES = [
        ('cerrado', 'Cerrado'),
        ('automatico', 'Automático (según horarios)'),
        ('abierto', 'Abierto'),
    ]

    nombre_local = models.CharField(max_length=100)
    direccion = models.CharField(max_length=255)
    telefono = models.CharField(max_length=20, blank=True, null=True)
    logo = models.ImageField(upload_to=get_restaurante_media_path, blank=True, null=True)
    color_principal = models.CharField(max_length=7, default='#A3E1BE')
    activo = models.BooleanField(default=True)
    tiene_demora = models.BooleanField(default=False, verbose_name="¿Hay demora en los pedidos?")
    tiempo_demora = models.CharField(max_length=50, blank=True, null=True, verbose_name="Tiempo estimado de demora")
    estado_control = models.CharField(
        max_length=10,
        choices=ESTADO_CONTROL_CHOICES,
        default='automatico',
        verbose_name="Control de estado del restaurante"
    )
    costo_envio = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        verbose_name="Costo de envío fijo"
    )
    umbral_envio_gratis = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        verbose_name="Monto mínimo para envío gratis"
    )
    codigos_descuento = JSONField(
        default=list, blank=True,
        verbose_name="Códigos de descuento"
    )
    meta_title = models.CharField(
        max_length=200, blank=True, null=True,
        verbose_name="Meta Título (SEO)"
    )
    meta_description = models.TextField(
        max_length=500, blank=True, null=True,
        verbose_name="Meta Descripción (SEO)"
    )
    meta_keywords = models.CharField(
        max_length=500, blank=True, null=True,
        verbose_name="Meta Palabras Clave (SEO, separadas por comas)"
    )
    written_schedules = models.TextField(
        max_length=500, blank=True, null=True,
        verbose_name="Horarios Escritos (ej. Lunes a Viernes 12:00-22:00)"
    )
    instagram_username = models.CharField(
        max_length=100, blank=True, null=True,
        verbose_name="Nombre de Usuario de Instagram"
    )
    facebook_username = models.CharField(
        max_length=100, blank=True, null=True,
        verbose_name="Nombre de Usuario de Facebook"
    )
    cash_discount_enabled = models.BooleanField(
        default=False,
        verbose_name="Habilitar descuento por pago en efectivo"
    )
    cash_discount_percentage = models.PositiveIntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(50)],
        verbose_name="Porcentaje de descuento por pago en efectivo"
    )

    def __str__(self):
        return self.username

    def esta_abierto(self):
        if self.estado_control == 'cerrado':
            return False
        if self.estado_control == 'abierto':
            return True
        ahora = timezone.localtime(timezone.now())
        dia_semana = ahora.weekday()
        hora_actual = ahora.time()
        horarios = self.horarios.filter(dia_semana=dia_semana)
        if not horarios.exists():
            return False
        for horario in horarios:
            if horario.hora_apertura <= hora_actual <= horario.hora_cierre:
                return True
        return False

    class Meta:
        indexes = [
            models.Index(fields=['username', 'activo']),
            models.Index(fields=['meta_title']),
            models.Index(fields=['meta_keywords']),
        ]

class HorarioRestaurante(models.Model):
    DIA_SEMANA_CHOICES = [
        (0, 'Lunes'),
        (1, 'Martes'),
        (2, 'Miércoles'),
        (3, 'Jueves'),
        (4, 'Viernes'),
        (5, 'Sábado'),
        (6, 'Domingo'),
    ]

    restaurante = models.ForeignKey(Restaurante, on_delete=models.CASCADE, related_name='horarios')
    dia_semana = models.IntegerField(choices=DIA_SEMANA_CHOICES, verbose_name="Día de la semana")
    hora_apertura = models.TimeField(verbose_name="Hora de apertura")
    hora_cierre = models.TimeField(verbose_name="Hora de cierre")

    class Meta:
        verbose_name = "Horario del Restaurante"
        verbose_name_plural = "Horarios del Restaurante"
        ordering = ['dia_semana', 'hora_apertura']

    def __str__(self):
        return f"{self.get_dia_semana_display()}: {self.hora_apertura} - {self.hora_cierre}"

class Categoria(models.Model):
    restaurante = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    nombre = models.CharField(max_length=100)
    orden = models.PositiveIntegerField(default=0)
    banner = models.ImageField(upload_to=get_restaurante_media_path, null=True, blank=True)

    class Meta:
        ordering = ['orden']
        indexes = [
            models.Index(fields=['restaurante', 'nombre']),
        ]

    def __str__(self):
        return self.nombre

    def delete(self, *args, **kwargs):
        if self.banner:
            if os.path.isfile(self.banner.path):
                os.remove(self.banner.path)
        super().delete(*args, **kwargs)

class Producto(models.Model):
    restaurante = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='productos')
    categoria = models.ForeignKey('Categoria', on_delete=models.SET_NULL, null=True, blank=True)
    nombre = models.CharField(max_length=100)
    descripcion = models.TextField(blank=True)
    precio = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0.00)])
    precio_original = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    tiene_descuento = models.BooleanField(default=False)
    imagen = models.ImageField(upload_to=get_restaurante_media_path, blank=True, null=True)
    disponible = models.BooleanField(default=True)
    stock = models.PositiveIntegerField(default=0, null=True, blank=True)
    agotado = models.BooleanField(default=False)
    orden = models.PositiveIntegerField(default=0)
    es_nuevo = models.BooleanField(default=False, verbose_name="¿Es nuevo?")
    fecha_marcado_nuevo = models.DateTimeField(null=True, blank=True)
    costo_produccion = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        verbose_name="Costo de producción"
    )

    def clean(self):
        if self.precio is None or self.precio < 0:
            raise ValidationError({'precio': 'El precio debe ser un número decimal no negativo válido.'})
        if self.costo_produccion is not None and self.costo_produccion < 0:
            raise ValidationError({'costo_produccion': 'El costo de producción debe ser positivo si se establece.'})
    # Solo validar relación entre precio y precio_original si tiene_descuento y discount_percentage > 0
        if self.tiene_descuento and getattr(self, 'discount_percentage', 0) > 0:
            if not self.precio_original:
                raise ValidationError({'precio_original': 'El precio original es requerido cuando se aplica un descuento.'})
            if self.precio_original <= 0:
                raise ValidationError({'precio_original': 'El precio original debe ser positivo si se establece.'})
        # Verificar que el precio con descuento sea consistente con el porcentaje
            calculated_price = (self.precio_original * (1 - Decimal(str(self.discount_percentage)) / 100)).quantize(Decimal('0.01'))
            if abs(self.precio - calculated_price) > Decimal('0.01'):  # Tolerancia para redondeos
                raise ValidationError({'precio': 'El precio con descuento debe coincidir con el porcentaje de descuento aplicado.'})

    def save(self, *args, **kwargs):
        self.full_clean()  # Run validation
        if self.es_nuevo and not self.fecha_marcado_nuevo:
            self.fecha_marcado_nuevo = timezone.now()
        elif not self.es_nuevo:
            self.fecha_marcado_nuevo = None
        if self.es_nuevo and self.fecha_marcado_nuevo:
            if timezone.now() > self.fecha_marcado_nuevo + timedelta(days=30):
                self.es_nuevo = False
                self.fecha_marcado_nuevo = None
        super().save(*args, **kwargs)

        # Actualizar todas las opciones asociadas
        categorias = OpcionCategoria.objects.filter(producto=self)
        for categoria in categorias:
            opciones = OpcionProducto.objects.filter(categoria=categoria)
            for opcion in opciones:
                # Actualizar el descuento de cada opción si tiene_descuento=True
                if opcion.tiene_descuento:
                    opcion.aplicar_descuento(self.discount_percentage if self.tiene_descuento else 0)
                    opcion.save()

    def delete(self, *args, **kwargs):
        if self.imagen:
            if os.path.isfile(self.imagen.path):
                os.remove(self.imagen.path)
        super().delete(*args, **kwargs)

    @property
    def ganancia_bruta(self):
        if self.costo_produccion is not None:
            return self.precio - self.costo_produccion
        return None

    @property
    def ganancia_bruta_abs(self):
        if self.ganancia_bruta is not None:
            return abs(self.ganancia_bruta)
        return None

    @property
    def discount_percentage(self):
        if self.tiene_descuento and self.precio_original:
            if self.precio_original == 0:
                return 0
            return int(((self.precio_original - self.precio) / self.precio_original) * 100)
        return 0

    class Meta:
        ordering = ['orden']

    def __str__(self):
        return f'{self.nombre} - {self.restaurante.nombre_local}'

    def reducir_stock(self, cantidad):
        if self.stock is not None:
            if self.stock >= cantidad:
                self.stock -= cantidad
                if self.stock <= 0:
                    self.agotado = True
                    self.stock = 0
                self.save()
                return True
            return False
        return True

class OpcionCategoria(models.Model):
    producto = models.ForeignKey(Producto, on_delete=models.CASCADE, related_name='opcion_categorias')
    nombre = models.CharField(max_length=100)
    max_selecciones = models.PositiveIntegerField(default=1, help_text="Númerodoğan de opciones que se pueden seleccionar en esta categoría")
    orden = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['orden']

    def __str__(self):
        return f"{self.nombre} ({self.producto.nombre})"

class OpcionProducto(models.Model):
    categoria = models.ForeignKey('OpcionCategoria', on_delete=models.CASCADE, related_name='opciones')
    nombre = models.CharField(max_length=100)
    precio_adicional = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, validators=[MinValueValidator(0.00)])
    precio_adicional_original = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)  # Nuevo campo
    tiene_descuento = models.BooleanField(default=False, verbose_name="Aplicar descuento del producto")
    agotado = models.BooleanField(default=False, verbose_name="Agotado")

    def clean(self):
        # Relajamos la validación: permitimos que precio_adicional sea None temporalmente
        if self.precio_adicional is not None and self.precio_adicional < 0:
            raise ValidationError({'precio_adicional': 'Additional price must be a valid non-negative decimal.'})

    def save(self, *args, **kwargs):
        self.full_clean()  # Run validation
        super().save(*args, **kwargs)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f"{self.nombre} ({self.categoria.producto.nombre})"

    def aplicar_descuento(self, discount_percentage):
        if not self.tiene_descuento or discount_percentage <= 0:
            self.tiene_descuento = False
            self.precio_adicional = self.precio_adicional_original or self.precio_adicional
            self.precio_adicional_original = None
            return
        # Guardamos el precio original si no está establecido
        if self.precio_adicional_original is None:
            self.precio_adicional_original = self.precio_adicional
        original_price = self.precio_adicional_original
        descuento = original_price * (Decimal(discount_percentage) / Decimal(100))
        self.precio_adicional = (original_price - descuento).quantize(Decimal('0.01'))
        self.tiene_descuento = True

class Pedido(models.Model):
    ESTADO_CHOICES = [
        ('pendiente', 'Pendiente'),
        ('pagado', 'Pagado'),
        ('en_preparacion', 'En preparación'),
        ('listo', 'Listo para entregar'),
        ('entregado', 'Entregado'),
        ('cancelado', 'Cancelado'),
        ('archivado', 'Archivado'),
        ('en_entrega', 'En entrega'),
    ]
    METODO_PAGO_CHOICES = [
        ('efectivo', 'Efectivo'),
        ('mercadopago', 'Mercado Pago'),
    ]
    TIPO_PEDIDO_CHOICES = [
        ('delivery', 'Delivery'),
        ('retiro', 'Retiro en Local'),
    ]
    TIEMPO_ESTIMADO_CHOICES = [
        ('15-30', 'Entre 15 y 30 minutos'),
        ('30-40', 'Entre 30 y 40 minutos'),
        ('45-60', 'Entre 45 y 60 minutos'),
        ('60-90', 'Entre 60 y 90 minutos'),
    ]
    MOTIVO_CANCELACION_CHOICES = [
        ('no_llegamos_zona', 'No llegamos hasta la zona indicada'),
        ('monto_minimo', 'No llega al monto mínimo'),
        ('datos_insuficientes', 'Datos del cliente insuficientes'),
        ('pago_incorrecto', 'Datos del medio de pago incorrectos'),
        ('cliente_cancelo', 'El cliente lo canceló'),
        ('falta_productos', 'Falta de productos del restaurante'),
        ('fuera_servicio', 'Restaurante fuera de servicio'),
        ('zona_cerrada', 'Zona de reparto cerrada'),
    ]

    restaurante = models.ForeignKey(Restaurante, on_delete=models.CASCADE, related_name='pedidos')
    numero_pedido = models.PositiveIntegerField(default=0)
    token = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)  # Added token field
    fecha = models.DateTimeField(auto_now_add=True)
    fecha_cancelado = models.DateTimeField(null=True, blank=True)
    fecha_en_entrega = models.DateTimeField(null=True, blank=True)
    cliente = models.CharField(max_length=100)
    telefono = models.CharField(max_length=20)
    metodo_pago = models.CharField(max_length=20, choices=METODO_PAGO_CHOICES)
    tipo_pedido = models.CharField(max_length=20, choices=TIPO_PEDIDO_CHOICES, default='retiro')
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='pendiente')
    tiempo_estimado = models.CharField(max_length=10, choices=TIEMPO_ESTIMADO_CHOICES, blank=True, null=True)
    motivo_cancelacion = models.CharField(max_length=50, choices=MOTIVO_CANCELACION_CHOICES, blank=True, null=True)
    direccion = models.CharField(max_length=255, blank=True, null=True)
    entrecalles = models.CharField(max_length=255, blank=True, null=True)
    impreso = models.BooleanField(default=False, verbose_name="Ticket impreso")
    aclaraciones = models.TextField(blank=True)
    total = models.DecimalField(max_digits=12, decimal_places=2)
    costo_envio = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, verbose_name="Costo de envío")
    codigo_descuento = models.CharField(max_length=50, blank=True, null=True, verbose_name="Código de descuento")
    monto_descuento = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, verbose_name="Monto del descuento")
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, verbose_name="Subtotal")
    cash_discount_applied = models.BooleanField(default=False)
    cash_discount_percentage = models.IntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(50)])

    def save(self, *args, **kwargs):
        if not self.id:
            ultimo_pedido = Pedido.objects.filter(restaurante=self.restaurante).order_by('-numero_pedido').first()
            if ultimo_pedido and ultimo_pedido.numero_pedido is not None:
                self.numero_pedido = ultimo_pedido.numero_pedido + 1
            else:
                self.numero_pedido = 1
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('confirmacion_pedido', kwargs={
            'nombre_restaurante': self.restaurante.username,
            'token': self.token  # Updated to use token
        })

    class Meta:
        ordering = ['-fecha']
        indexes = [
            models.Index(fields=['token']),  # Added index for token
        ]

    def __str__(self):
        return f"Pedido #{self.numero_pedido} - {self.cliente}"

class ItemPedido(models.Model):
    pedido = models.ForeignKey(Pedido, on_delete=models.CASCADE, related_name='items')
    producto = models.ForeignKey(Producto, on_delete=models.SET_NULL, null=True)
    nombre_producto = models.CharField(max_length=100)
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2)
    cantidad = models.PositiveIntegerField(default=1)
    opciones_seleccionadas = JSONField(default=list, blank=True)

    @property
    def subtotal(self):
        return self.precio_unitario * self.cantidad

    def __str__(self):
        return f"{self.cantidad}x {self.nombre_producto}"
    

def get_qr_upload_path(instance, filename):
    # Use no-space slug for filename (e.g., "Hot 100" -> "hot100_qr.png")
    safe_name = instance.name.replace(' ', '').lower()
    return os.path.join('qrcodes', f"{safe_name}_qr.png")

class RestaurantQR(models.Model):
    name = models.CharField(max_length=100, unique=True, help_text="Nombre del restaurante")
    qr_image = models.ImageField(upload_to=get_qr_upload_path, blank=True, null=True, help_text="Imagen del QR generada")
    url = models.URLField(max_length=200, blank=True, help_text="URL asociada al QR")
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.qr_image and self.url:
            qr = qrcode.QRCode(version=1, box_size=10, border=4)
            qr.add_data(self.url)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            img_name = f"{self.name.replace(' ', '').lower()}_qr.png"
            img_path = os.path.join('/app/media/qrcodes', img_name)
            os.makedirs(os.path.dirname(img_path), exist_ok=True)
            img.save(img_path)
            with open(img_path, 'rb') as f:
                self.qr_image.save(img_name, File(f), save=False)
            super().save(*args, **kwargs)

    def __str__(self):
        return self.name
