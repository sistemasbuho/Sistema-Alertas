import json
import logging
import os
import time
import traceback

import requests
from django.utils import timezone


logger = logging.getLogger('api_requests')


class RequestLoggingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.api_url = os.getenv('API_TOC_URL')

    def __call__(self, request):
        start_time = time.time()

        user_id = None
        user_email = 'anonymous'

        if hasattr(request, 'user') and request.user.is_authenticated:
            user_id = request.user.id
            user_email = request.user.email
        elif 'HTTP_AUTHORIZATION' in request.META:
            auth_header = request.META.get('HTTP_AUTHORIZATION', '')
            if auth_header.startswith('Bearer ') or auth_header.startswith('JWT '):
                try:
                    from rest_framework_simplejwt.tokens import AccessToken

                    token = auth_header.split(' ')[1]
                    decoded_token = AccessToken(token, verify=False)
                    user_id = decoded_token.get('user_id')

                    if user_id:
                        from django.contrib.auth import get_user_model

                        User = get_user_model()
                        try:
                            user = User.objects.get(id=user_id)
                            user_email = user.email
                        except User.DoesNotExist:
                            pass
                except Exception:
                    pass

        request_data = {
            'timestamp': timezone.now().isoformat(),
            'method': request.method,
            'path': request.path,
            'user_id': user_id,
            'user': user_email,
            'ip': self.get_client_ip(request),
            'user_agent': request.META.get('HTTP_USER_AGENT', ''),
            'query_params': self.get_query_params(request),
            'correlation_id': self.get_correlation_id(request),
        }

        if request.method in ['POST', 'PUT', 'PATCH'] and hasattr(request, 'body'):
            body_preview = self.get_request_body_preview(request)
            if body_preview is not None:
                request_data['request_body_preview'] = body_preview

        try:
            response = self.get_response(request)

            duration = time.time() - start_time
            request_data.update(
                {
                    'status_code': response.status_code,
                    'duration': duration,
                    'content_length': len(response.content) if hasattr(response, 'content') else 0,
                    'is_error': False,
                }
            )

            self.send_to_external_api(request_data)

            return response

        except Exception as exception:  # noqa: BLE001
            tb = traceback.format_exc()
            duration = time.time() - start_time

            request_data.update(
                {
                    'status_code': 500,
                    'duration': duration,
                    'content_length': 0,
                    'is_error': True,
                    'error_type': exception.__class__.__name__,
                    'error_message': str(exception),
                    'error_traceback': tb,
                }
            )

            self.send_to_external_api(request_data)

            raise

    def get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip

    def get_query_params(self, request):
        try:
            return {
                key: values if len(values) > 1 else values[0]
                for key, values in request.GET.lists()
            }
        except Exception:
            return dict(request.GET.items())

    def get_correlation_id(self, request):
        return (
            request.META.get('HTTP_X_CORRELATION_ID')
            or request.META.get('HTTP_CORRELATION_ID')
            or request.META.get('HTTP_X_REQUEST_ID')
        )

    def get_request_body_preview(self, request, max_length=1000):
        if not request.body:
            return ''

        try:
            raw_body = request.body.decode('utf-8')
        except UnicodeDecodeError:
            return '[non-text body]'

        try:
            body_data = json.loads(raw_body)
            if isinstance(body_data, dict):
                body_data = self._mask_sensitive_data(body_data)
            preview = json.dumps(body_data)
        except (ValueError, TypeError):
            preview = raw_body

        return preview[:max_length]

    def _mask_sensitive_data(self, data):
        if not isinstance(data, dict):
            return data

        masked = {}
        for key, value in data.items():
            if isinstance(value, dict):
                value = self._mask_sensitive_data(value)
            if isinstance(value, list):
                value = [self._mask_sensitive_data(item) for item in value]

            if key.lower() in {'password', 'token'}:
                masked[key] = '********'
            else:
                masked[key] = value
        return masked

    def send_to_external_api(self, request_data):
        if not self.api_url:
            logger.error('API_TOC_URL no está configurado. No se enviará el log.')
            return

        payload = {
            'user_email': request_data.get('user'),
            'plataforma_id': 11,
            'timestamp': request_data.get('timestamp'),
            'method': request_data.get('method'),
            'path': request_data.get('path'),
            'status_code': request_data.get('status_code'),
            'duration_ms': int((request_data.get('duration') or 0) * 1000),
            'ip_address': request_data.get('ip'),
            'user_agent': request_data.get('user_agent', ''),
            'query_params': request_data.get('query_params') or {},
            'request_body_preview': request_data.get('request_body_preview', ''),
            'is_error': request_data.get('is_error', False),
            'error_type': request_data.get('error_type'),
            'error_message': request_data.get('error_message'),
            'error_traceback': request_data.get('error_traceback'),
            'correlation_id': request_data.get('correlation_id'),
        }

        try:
            response = requests.post(self.api_url, json=payload, timeout=5)
            if response.status_code >= 400:
                logger.error(
                    'Falló el envío del log a la API externa. Código: %s, Respuesta: %s',
                    response.status_code,
                    response.text,
                )
        except requests.RequestException as exc:
            logger.error('Error enviando log a la API externa: %s', exc)
