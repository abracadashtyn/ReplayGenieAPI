from flask_restx import fields

from app.api.v1 import api_v1


error_response = api_v1.model('ErrorResponse', {
    'success': fields.Boolean(default=False),
    'error': fields.Nested(api_v1.model('ErrorDetail', {
        'code': fields.String,
        'message': fields.String,
        'details': fields.Raw,
    }))
})

class APIError(Exception):
    def __init__(self, message, code='INTERNAL_ERROR', status=500, details=None):
        self.message = message
        self.code = code
        self.status = status
        self.details = details or {}

class NotFoundError(APIError):
    def __init__(self, message, details=None):
        super().__init__(message, code='NOT_FOUND', status=404, details=details)

class ValidationError(APIError):
    def __init__(self, message, details=None):
        super().__init__(message, code='VALIDATION_ERROR', status=400, details=details)

# handler for the specific Errors defined above
@api_v1.errorhandler(APIError)
def handle_api_error(error):
    return {
        'success': False,
        'error': {
            'code': error.code,
            'message': error.message,
            'details': error.details
        }
    }, error.status

# generic error handler for any Exceptions not caught by the above
@api_v1.errorhandler(Exception)
def handle_error(error):
    return {
        'success': False,
        'error': {
            'code': 'INTERNAL_ERROR',
            'message': 'Internal server error',
            'details': {}
        }
    }, 500