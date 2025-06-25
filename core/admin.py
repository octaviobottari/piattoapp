from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import Restaurante, Producto

@admin.register(Restaurante)
class RestauranteAdmin(UserAdmin):
    model = Restaurante
    list_display = ('username', 'nombre_local', 'direccion', 'telefono', 'is_staff')
    fieldsets = UserAdmin.fieldsets + (
        ('Información del Restaurante', {
            'fields': ('nombre_local', 'direccion', 'telefono')
        }),
    )
admin.site.register(Producto)

