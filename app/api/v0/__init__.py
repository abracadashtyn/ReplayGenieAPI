from flask import Blueprint
from flask_restx import Api, fields


bp = Blueprint('api', __name__, url_prefix='/api/v0')
api = Api(
    bp,
    version='0.1',
    title='ReplayGenie API',
    doc='/docs'
)

pagination_model = api.model('Pagination', {
    'page': fields.Integer,
    'items_per_page': fields.Integer,
    'total_items': fields.Integer,
    'total_pages': fields.Integer
})
no_count_pagination_model = api.model('NoCountPagination', {
    'page': fields.Integer,
    'items_per_page': fields.Integer,
    'has_next': fields.Boolean,
})
error_response = api.model('ErrorResponse', {
    'success': fields.Boolean(description='Always false for errors', default=False),
    'error': fields.String(description='Error message', required=True)
})

# Global handler for unexpected errors that don't have their own handler defined
@api.errorhandler(Exception)
def handle_error(error):
    return {'success': False, 'error': 'Internal server error'}, 500

from app.api.v0 import abilities_namespace, config_namespace, formats_namespace, items_namespace, matches_namespace,\
                        moves_namespace, players_namespace, pokemon_namespace, sets_namespace, types_namespace
