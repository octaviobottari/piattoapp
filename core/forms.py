# core/forms.py
from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from .models import Restaurante, Producto, Categoria, HorarioRestaurante, OpcionProducto, OpcionCategoria
from django.forms import inlineformset_factory
from decimal import Decimal, InvalidOperation, ROUND_DOWN

# Definir las constantes al principio del archivo
HOUR_CHOICES = [(f"{i:02d}", f"{i:02d}") for i in range(24)]  # 00 a 23
MINUTE_CHOICES = [('00', '00'), ('15', '15'), ('30', '30'), ('45', '45')]  # Incrementos de 15 minutos

class RegistroRestauranteForm(UserCreationForm):
    class Meta:
        model = Restaurante
        fields = ['username', 'nombre_local', 'direccion', 'telefono', 'password1', 'password2']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control'}),
            'nombre_local': forms.TextInput(attrs={'class': 'form-control'}),
            'direccion': forms.TextInput(attrs={'class': 'form-control'}),
            'telefono': forms.TextInput(attrs={'class': 'form-control'}),
        }

class LoginForm(AuthenticationForm):
    username = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-control'}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-control'}))

class ProductoForm(forms.ModelForm):
    nueva_categoria = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nueva categoría (opcional)'})
    )
    banner = forms.ImageField(
        required=False,
        widget=forms.FileInput(attrs={'class': 'form-control'}),
        label='Banner (1161 x 226 px recomendado)'
    )

    class Meta:
        model = Producto
        fields = [
            'categoria', 'nueva_categoria', 'nombre', 'descripcion', 'precio',
            'imagen', 'stock', 'agotado', 'disponible', 'es_nuevo', 'costo_produccion'
        ]
        widgets = {
            'categoria': forms.Select(attrs={'class': 'form-control'}),
            'nombre': forms.TextInput(attrs={'class': 'form-control'}),
            'descripcion': forms.Textarea(attrs={'class': 'form-control'}),
            'precio': forms.NumberInput(attrs={'class': 'form-control precio-input', 'inputmode': 'decimal', 'step': '0.01', 'min': '0'}),
            'imagen': forms.FileInput(attrs={'class': 'form-control'}),
            'stock': forms.NumberInput(attrs={'class': 'form-control', 'step': '1', 'min': '0'}),
            'agotado': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'disponible': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'es_nuevo': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'costo_produccion': forms.NumberInput(attrs={
                'class': 'form-control precio-input',
                'inputmode': 'decimal',
                'step': '0.01',
                'min': '0'
            }),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if user:
            self.fields['categoria'].queryset = Categoria.objects.filter(restaurante=user)

    def clean(self):
        cleaned_data = super().clean()
        precio = cleaned_data.get('precio')
        costo_produccion = cleaned_data.get('costo_produccion')
        stock = cleaned_data.get('stock')

        # Validate precio
        if precio is not None:
            try:
                # Ensure precio is a Decimal with max 2 decimal places
                precio_decimal = Decimal(str(precio))
                decimal_places = abs(precio_decimal.as_tuple().exponent)
                if decimal_places > 2:
                    self.add_error('precio', 'El precio no puede tener más de 2 decimales.')
                if precio_decimal < 0:
                    self.add_error('precio', 'El precio debe ser mayor o igual a 0.')
                cleaned_data['precio'] = precio_decimal
            except (ValueError, InvalidOperation):
                self.add_error('precio', 'El precio debe ser un número válido.')

        # Validate costo_produccion
        if costo_produccion is not None:
            try:
                costo_decimal = Decimal(str(costo_produccion)) if costo_produccion != '' else None
                if costo_decimal is not None:
                    decimal_places = abs(costo_decimal.as_tuple().exponent)
                    if decimal_places > 2:
                        self.add_error('costo_produccion', 'El costo de producción no puede tener más de 2 decimales.')
                    if costo_decimal < 0:
                        self.add_error('costo_produccion', 'El costo de producción debe ser mayor o igual a 0.')
                cleaned_data['costo_produccion'] = costo_decimal
            except (ValueError, InvalidOperation):
                self.add_error('costo_produccion', 'El costo de producción debe ser un número válido.')

        # Validate stock
        if stock is not None:
            try:
                cleaned_data['stock'] = int(float(stock))
                if cleaned_data['stock'] < 0:
                    self.add_error('stock', 'El stock debe ser mayor o igual a 0.')
            except (ValueError, TypeError):
                self.add_error('stock', 'El stock debe ser un número entero.')

        return cleaned_data

class OpcionProductoForm(forms.ModelForm):
    original_price = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=False,
        label="Precio Original",
        widget=forms.NumberInput(attrs={'class': 'form-control original-price', 'step': '0.01', 'min': '0'})
    )

    class Meta:
        model = OpcionProducto
        fields = ['id', 'nombre', 'agotado', 'tiene_descuento', 'original_price']
        widgets = {
            'id': forms.HiddenInput(),
            'nombre': forms.TextInput(attrs={'class': 'form-control'}),
            'agotado': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'tiene_descuento': forms.CheckboxInput(attrs={'class': 'form-check-input tiene-descuento'}),
        }

    def __init__(self, *args, **kwargs):
        self.producto = kwargs.pop('producto', None)
        super().__init__(*args, **kwargs)
        self.fields['nombre'].required = False
        self.fields['tiene_descuento'].required = False
        if self.instance and self.instance.pk and self.instance.tiene_descuento and self.producto and self.producto.tiene_descuento and self.producto.discount_percentage:
            discount_percentage = Decimal(str(self.producto.discount_percentage))
            divisor = (Decimal('100') - discount_percentage) / Decimal('100')
            self.initial['original_price'] = round(self.instance.precio_adicional_original or self.instance.precio_adicional / divisor, 2)
        elif self.instance and self.instance.pk:
            self.initial['original_price'] = self.instance.precio_adicional_original or self.instance.precio_adicional

    def clean(self):
        cleaned_data = super().clean()
        nombre = cleaned_data.get('nombre')
        original_price = cleaned_data.get('original_price')
        tiene_descuento = cleaned_data.get('tiene_descuento')
        delete = cleaned_data.get('DELETE', False)

        # Debugging
        print(f"Cleaning OpcionProductoForm: nombre={nombre}, original_price={original_price}, tiene_descuento={tiene_descuento}, delete={delete}")

        # Mark incomplete options for deletion
        if not delete and (not nombre or original_price is None):
            cleaned_data['DELETE'] = True
            return cleaned_data

        if not delete:
            if original_price is not None:
                if original_price < 0:
                    self.add_error('original_price', 'El precio original debe ser un valor no negativo.')
                else:
                    # Normalizar y verificar que no haya más de 2 decimales
                    price_str = str(original_price).strip()
                    price_str = price_str.replace('.', ',')  # Asegurar que usamos coma como separador
                    try:
                        decimal_value = Decimal(price_str.replace(',', '.'))
                        decimal_places = abs(decimal_value.as_tuple().exponent)
                        if decimal_places > 2:
                            self.add_error('original_price', 'El precio original no puede tener más de 2 decimales.')
                        cleaned_data['original_price'] = decimal_value.quantize(Decimal('0.01'), rounding=ROUND_DOWN)
                    except (ValueError, InvalidOperation):
                        self.add_error('original_price', 'El precio original debe ser un número válido.')
            # Calcular precio_adicional y precio_adicional_original
            if tiene_descuento and self.producto and self.producto.tiene_descuento and self.producto.discount_percentage and self.producto.discount_percentage > 0:
                discount_percentage = Decimal(str(self.producto.discount_percentage))
                divisor = (Decimal('100') - discount_percentage) / Decimal('100')
                self.instance.precio_adicional_original = original_price
                self.instance.precio_adicional = round(original_price * divisor, 2)
                self.instance.tiene_descuento = True
                print(f"Applied discount: precio_adicional={self.instance.precio_adicional}, precio_adicional_original={self.instance.precio_adicional_original}")
            elif tiene_descuento:
                # Si tiene_descuento es True pero no hay descuento en el producto, mostrar error
                self.add_error('tiene_descuento', 'No se puede aplicar descuento porque el producto no tiene un porcentaje de descuento configurado.')
                self.instance.tiene_descuento = False
                self.instance.precio_adicional = original_price
                self.instance.precio_adicional_original = None
                print(f"Discount error: precio_adicional={self.instance.precio_adicional}, precio_adicional_original={self.instance.precio_adicional_original}")
            else:
                self.instance.precio_adicional = original_price
                self.instance.precio_adicional_original = None
                self.instance.tiene_descuento = False
                print(f"No discount: precio_adicional={self.instance.precio_adicional}, precio_adicional_original={self.instance.precio_adicional_original}")

        return cleaned_data

    def save(self, *args, **kwargs):
        if self.cleaned_data.get('DELETE', False):
            if self.instance.pk:
                self.instance.delete()
            return None
        return super().save(*args, **kwargs)

class OpcionCategoriaForm(forms.ModelForm):
    class Meta:
        model = OpcionCategoria
        fields = ['id', 'nombre', 'max_selecciones']
        widgets = {
            'id': forms.HiddenInput(),
            'nombre': forms.TextInput(attrs={'class': 'form-control'}),
            'max_selecciones': forms.NumberInput(attrs={'class': 'form-control', 'min': '1', 'max': '100'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['nombre'].required = False
        self.fields['max_selecciones'].required = False

    def clean(self):
        cleaned_data = super().clean()
        nombre = cleaned_data.get('nombre')
        max_selecciones = cleaned_data.get('max_selecciones')
        delete = cleaned_data.get('DELETE', False)

        if not delete and nombre:
            if not nombre:
                self.add_error('nombre', 'El nombre es obligatorio para categorías no eliminadas.')
            if max_selecciones is None:
                self.add_error('max_selecciones', 'El número máximo de selecciones es obligatorio.')
            elif max_selecciones < 1 or max_selecciones > 100:
                self.add_error('max_selecciones', 'El número máximo de selecciones debe estar entre 1 y 100.')

        return cleaned_data
    
class HorarioRestauranteForm(forms.ModelForm):
    hora_apertura_hora = forms.ChoiceField(
        choices=HOUR_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select hora-select'}),
        label="Hora de apertura"
    )
    hora_apertura_minuto = forms.ChoiceField(
        choices=MINUTE_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select minuto-select'}),
        label="Minutos"
    )
    hora_cierre_hora = forms.ChoiceField(
        choices=HOUR_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select hora-select'}),
        label="Hora de cierre"
    )
    hora_cierre_minuto = forms.ChoiceField(
        choices=MINUTE_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select minuto-select'}),
        label="Minutos"
    )

    class Meta:
        model = HorarioRestaurante
        fields = ['dia_semana', 'hora_apertura', 'hora_cierre']
        widgets = {
            'dia_semana': forms.HiddenInput(),  # Change to HiddenInput
            'hora_apertura': forms.HiddenInput(),
            'hora_cierre': forms.HiddenInput(),
        }

    def clean(self):
        cleaned_data = super().clean()
        hora_apertura_hora = cleaned_data.get('hora_apertura_hora')
        hora_apertura_minuto = cleaned_data.get('hora_apertura_minuto')
        hora_cierre_hora = cleaned_data.get('hora_cierre_hora')
        hora_cierre_minuto = cleaned_data.get('hora_cierre_minuto')

        if hora_apertura_hora and hora_apertura_minuto:
            cleaned_data['hora_apertura'] = f"{hora_apertura_hora}:{hora_apertura_minuto}:00"
        if hora_cierre_hora and hora_cierre_minuto:
            cleaned_data['hora_cierre'] = f"{hora_cierre_hora}:{hora_cierre_minuto}:00"

        hora_apertura = cleaned_data.get('hora_apertura')
        hora_cierre = cleaned_data.get('hora_cierre')

        if hora_apertura and hora_cierre and hora_apertura >= hora_cierre:
            raise forms.ValidationError("La hora de apertura debe ser anterior a la hora de cierre.")
        return cleaned_data

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            if self.instance.hora_apertura:
                self.initial['hora_apertura_hora'] = self.instance.hora_apertura.strftime('%H')
                self.initial['hora_apertura_minuto'] = self.instance.hora_apertura.strftime('%M')
            if self.instance.hora_cierre:
                self.initial['hora_cierre_hora'] = self.instance.hora_cierre.strftime('%H')
                self.initial['hora_cierre_minuto'] = self.instance.hora_cierre.strftime('%M')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Si hay un valor inicial para hora_apertura y hora_cierre, lo separamos en hora y minuto
        if self.instance and self.instance.pk:
            if self.instance.hora_apertura:
                self.initial['hora_apertura_hora'] = self.instance.hora_apertura.strftime('%H')
                self.initial['hora_apertura_minuto'] = self.instance.hora_apertura.strftime('%M')
            if self.instance.hora_cierre:
                self.initial['hora_cierre_hora'] = self.instance.hora_cierre.strftime('%H')
                self.initial['hora_cierre_minuto'] = self.instance.hora_cierre.strftime('%M')

# Formset para manejar múltiples horarios
HorarioRestauranteFormSet = inlineformset_factory(
    Restaurante,
    HorarioRestaurante,
    form=HorarioRestauranteForm,
    extra=1,
    can_delete=True,
    min_num=0,
    validate_min=True,
)

class RestauranteDemoraForm(forms.ModelForm):
    class Meta:
        model = Restaurante
        fields = ['tiene_demora', 'tiempo_demora']
        widgets = {
            'tiene_demora': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'tiempo_demora': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej. 15-30 minutos'}),
        }


class ConfigRestauranteForm(forms.ModelForm):
    class Meta:
        model = Restaurante
        fields = [
            'costo_envio', 'umbral_envio_gratis', 'meta_title', 'meta_description',
            'meta_keywords', 'logo', 'direccion', 'written_schedules', 'telefono',
            'instagram_username', 'facebook_username'
        ]
        widgets = {
            'costo_envio': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ej. 500.00',
                'step': '0.01',
                'min': '0'
            }),
            'umbral_envio_gratis': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ej. 5000.00',
                'step': '0.01',
                'min': '0'
            }),
            'meta_title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ej. Mejor Hamburguesa en Buenos Aires'
            }),
            'meta_description': forms.Textarea(attrs={
                'class': 'form-control',
                'placeholder': 'Ej. Deliciosas hamburguesas caseras con entrega rápida.',
                'rows': 4
            }),
            'meta_keywords': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ej. hamburguesas, comida rápida, delivery, Buenos Aires'
            }),
            'logo': forms.FileInput(attrs={'class': 'form-control'}),
            'direccion': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ej. Av. Corrientes 1234, Buenos Aires'
            }),
            'written_schedules': forms.Textarea(attrs={
                'class': 'form-control',
                'placeholder': 'Ej. Lunes a Viernes 12:00-22:00, Sábado 12:00-23:00',
                'rows': 4
            }),
            'telefono': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ej. +541123456789'
            }),
            'instagram_username': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ej. hvn_burger'
            }),
            'facebook_username': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ej. HVNBurger'
            }),
        }

class CodigoDescuentoForm(forms.Form):
    nombre_codigo = forms.CharField(
        max_length=50,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Ej. DESC10'
        }),
        label="Nombre del código"
    )
    porcentaje = forms.ChoiceField(
        choices=[(i, f"{i}%") for i in range(5, 101, 5)],
        widget=forms.Select(attrs={'class': 'form-control'}),
        label="Porcentaje de descuento"
    )