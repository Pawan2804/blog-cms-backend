from rest_framework.views import exception_handler


STATUS_CODES = {
    400: 'validation_error',
    401: 'authentication_error',
    403: 'permission_denied',
    404: 'not_found',
    405: 'method_not_allowed',
    429: 'rate_limited',
}


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is None:
        return None

    raw_data = response.data
    status_code = response.status_code
    code = STATUS_CODES.get(status_code, 'api_error')

    if isinstance(raw_data, dict) and 'detail' in raw_data:
        message = str(raw_data['detail'])
        details = {}
    elif status_code == 400:
        message = 'Request validation failed.'
        details = raw_data
    elif isinstance(raw_data, list):
        message = 'Request could not be processed.'
        details = raw_data
    else:
        message = 'Request could not be processed.'
        details = raw_data

    response.data = {
        'error': {
            'code': code,
            'message': message,
            'details': details,
        }
    }
    return response
