from django.http import HttpResponse


class DevCorsMiddleware:
    """Allow local frontend origins to call API endpoints during development."""

    ALLOWED_ORIGINS = {
        'http://localhost:5173',
        'http://127.0.0.1:5173',
    }

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        origin = request.headers.get('Origin', '')
        is_api_request = request.path.startswith('/api/')

        if request.method == 'OPTIONS' and is_api_request:
            response = HttpResponse(status=204)
            return self._add_cors_headers(response, origin)

        response = self.get_response(request)
        if is_api_request:
            response = self._add_cors_headers(response, origin)
        return response

    def _add_cors_headers(self, response, origin):
        if origin in self.ALLOWED_ORIGINS:
            response['Access-Control-Allow-Origin'] = origin
            response['Vary'] = 'Origin'
            response['Access-Control-Allow-Methods'] = 'GET, POST, PUT, PATCH, DELETE, OPTIONS'
            response['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Requested-With'
        return response
