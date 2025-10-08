from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django import forms
from django.contrib.auth.forms import UserChangeForm, UserCreationForm
from .models import Restaurante, Producto

class RestauranteCreationForm(UserCreationForm):
    class Meta:
        model = Restaurante
        fields = ('username', 'nombre_local', 'direccion', 'telefono')

class RestauranteChangeForm(UserChangeForm):
    class Meta:
        model = Restaurante
        fields = '__all__'

@admin.register(Restaurante)
class RestauranteAdmin(UserAdmin):
    form = RestauranteChangeForm
    add_form = RestauranteCreationForm
    
    model = Restaurante
    list_display = ('username', 'nombre_local', 'direccion', 'telefono', 'is_staff', 'is_active')
    list_filter = ('is_staff', 'is_active', 'estado_control')
    search_fields = ('username', 'nombre_local', 'direccion')
    
    fieldsets = UserAdmin.fieldsets + (
        ('Información del Restaurante', {
            'fields': (
                'nombre_local', 
                'direccion', 
                'telefono',
                'logo',
                'color_principal',
                'activo',
                'estado_control',
                'costo_envio',
                'umbral_envio_gratis',
                'cash_discount_enabled',
                'cash_discount_percentage',
                'metodo_pago_mercadopago',
                'metodo_pago_alias',
                'alias_cbu',
                'mp_access_token',
                'mp_refresh_token',
                'mp_user_id',
                'mp_token_expires_at'
            )
        }),
        ('SEO y Redes Sociales', {
            'fields': (
                'meta_title',
                'meta_description', 
                'meta_keywords',
                'written_schedules',
                'instagram_username',
                'facebook_username'
            )
        }),
        ('Códigos de Descuento', {
            'fields': ('codigos_descuento',)
        }),
    )
    
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Información del Restaurante', {
            'fields': (
                'nombre_local', 
                'direccion', 
                'telefono',
                'email'
            )
        }),
    )
    
    def get_form(self, request, obj=None, **kwargs):
        """
        Use special form during user creation
        """
        defaults = {}
        if obj is None:
            defaults['form'] = self.add_form
        defaults.update(kwargs)
        return super().get_form(request, obj, **defaults)

admin.site.register(Producto)