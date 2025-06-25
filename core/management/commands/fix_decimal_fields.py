from django.core.management.base import BaseCommand
from django.db.models import Q
from decimal import Decimal, InvalidOperation
from core.models import Producto, OpcionProducto
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Fixes invalid Decimal values in Producto and OpcionProducto models'

    def handle(self, *args, **options):
        self.stdout.write("Starting Decimal field cleanup...")

        # Fix Producto model
        producto_count = 0
        for producto in Producto.objects.all():
            try:
                needs_save = False
                logger.info(f"Inspecting Producto ID {producto.id}: {producto.nombre}")
                
                # Check precio (non-nullable, must be valid Decimal)
                if producto.precio is None or isinstance(producto.precio, str) or producto.precio < 0:
                    logger.info(f" - Invalid precio: {producto.precio}")
                    producto.precio = Decimal('0.00')
                    needs_save = True
                
                # Check precio_original (nullable, must be valid if set)
                if producto.precio_original is not None:
                    if isinstance(producto.precio_original, str) or producto.precio_original <= 0:
                        logger.info(f" - Invalid precio_original: {producto.precio_original}")
                        producto.precio_original = None
                        needs_save = True
                
                # Check costo_produccion (nullable, must be valid if set)
                if producto.costo_produccion is not None:
                    if isinstance(producto.costo_produccion, str) or producto.costo_produccion <= 0:
                        logger.info(f" - Invalid costo_produccion: {producto.costo_produccion}")
                        producto.costo_produccion = None
                        needs_save = True
                
                # Check discount_percentage (non-nullable, must be valid Decimal)
                if (producto.discount_percentage is None or 
                    isinstance(producto.discount_percentage, str) or 
                    producto.discount_percentage < 0 or 
                    producto.discount_percentage > 100):
                    logger.info(f" - Invalid discount_percentage: {producto.discount_percentage}")
                    producto.discount_percentage = Decimal('0.00')
                    needs_save = True
                
                # Test ganancia_bruta if it exists
                if hasattr(producto, 'ganancia_bruta'):
                    try:
                        ganancia = producto.ganancia_bruta
                        logger.info(f" - ganancia_bruta: {ganancia}")
                    except InvalidOperation as e:
                        logger.error(f" - InvalidOperation in ganancia_bruta: {e}")
                        # Reset problematic fields to safe values
                        producto.costo_produccion = None
                        producto.discount_percentage = Decimal('0.00')
                        needs_save = True
                
                if needs_save:
                    producto.save()
                    producto_count += 1
                    logger.info(f" - Saved fixes for Producto ID {producto.id}")
            
            except Exception as e:
                logger.error(f"Error processing Producto ID {producto.id}: {e}", exc_info=True)
        
        # Fix OpcionProducto model
        opcion_count = 0
        for opcion in OpcionProducto.objects.all():
            try:
                needs_save = False
                logger.info(f"Inspecting OpcionProducto ID {opcion.id}: {opcion.nombre}")
                
                # Check precio_adicional (non-nullable, must be valid Decimal)
                if opcion.precio_adicional is None or isinstance(opcion.precio_adicional, str) or opcion.precio_adicional < 0:
                    logger.info(f" - Invalid precio_adicional: {opcion.precio_adicional}")
                    opcion.precio_adicional = Decimal('0.00')
                    needs_save = True
                
                # Check precio_adicional_original (nullable, must be valid if set)
                if opcion.precio_adicional_original is not None:
                    if isinstance(opcion.precio_adicional_original, str) or opcion.precio_adicional_original <= 0:
                        logger.info(f" - Invalid precio_adicional_original: {opcion.precio_adicional_original}")
                        opcion.precio_adicional_original = None
                        needs_save = True
                
                if needs_save:
                    opcion.save()
                    opcion_count += 1
                    logger.info(f" - Saved fixes for OpcionProducto ID {opcion.id}")
            
            except Exception as e:
                logger.error(f"Error processing OpcionProducto ID {opcion.id}: {e}", exc_info=True)

        self.stdout.write(f"Cleanup complete: Fixed {producto_count} Producto and {opcion_count} OpcionProducto records.")