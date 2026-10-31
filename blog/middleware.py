import logging
import time
import uuid


logger = logging.getLogger('blog.request')


class RequestLoggingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = request.headers.get('X-Request-ID') or str(uuid.uuid4())
        request.request_id = request_id
        started_at = time.perf_counter()

        try:
            response = self.get_response(request)
        except Exception:
            logger.exception(
                'request.failed',
                extra={
                    'request_id': request_id,
                    'method': request.method,
                    'path': request.path,
                    'duration_ms': round((time.perf_counter() - started_at) * 1000, 2),
                },
            )
            raise

        response['X-Request-ID'] = request_id
        logger.info(
            'request.complete',
            extra={
                'request_id': request_id,
                'method': request.method,
                'path': request.path,
                'status_code': response.status_code,
                'duration_ms': round((time.perf_counter() - started_at) * 1000, 2),
            },
        )
        return response
