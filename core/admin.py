from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import Restaurante, Producto

@admin.register(Restaurante)
class RestauranteAdmin(UserAdmin):
    # Campos para mostrar en la lista
    list_display = ('username', 'nombre_local', 'direccion', 'telefono', 'is_staff', 'is_active')
    list_filter = ('is_staff', 'is_active')
    search_fields = ('username', 'nombre_local', 'direccion')
    
    # Campos para la EDICIÓN (cuando ya existe el usuario)
    fieldsets = (
        (None, {
            'fields': ('username', 'password')
        }),
        ('Información Personal', {
            'fields': ('first_name', 'last_name', 'email')
        }),
        ('Permisos', {
            'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')
        }),
        ('Fechas importantes', {
            'fields': ('last_login', 'date_joined')
        }),
        ('Información del Restaurante', {
            'fields': ('nombre_local', 'direccion', 'telefono')
        }),
    )
    
    # Campos para la CREACIÓN (nuevo usuario)
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'password1', 'password2'),
        }),
        ('Información del Restaurante', {
            'fields': ('nombre_local', 'direccion', 'telefono')
        }),
        ('Permisos', {
            'fields': ('is_active', 'is_staff', 'is_superuser')
        }),
    )

@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'restaurante', 'precio', 'disponible')
    list_filter = ('restaurante', 'disponible')
    search_fields = ('nombre', 'restaurante__username')