import logging
from django.http import JsonResponse
from django.shortcuts import render

logger = logging.getLogger(__name__)

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