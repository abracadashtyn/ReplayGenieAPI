from flask import Blueprint
from flask_restx import Api, fields


bp = Blueprint('api_v0', __name__, url_prefix='/api/v0')
api_v0 = Api(
    bp,
    version='0.1',
    title='ReplayGenie API',
    doc='/docs'
)

error_response = api_v0.model('ErrorResponse', {
    'success': fields.Boolean(description='Always false for errors', default=False),
    'error': fields.String(description='Error message', required=True)
})

# Global handler for unexpected errors that don't have their own handler defined
@api_v0.errorhandler(Exception)
def handle_error(error):
    return {'success': False, 'error': 'Internal server error'}, 500

from app.api.v0 import abilities_namespace, config_namespace, formats_namespace, items_namespace, matches_namespace,\
                        moves_namespace, players_namespace, pokemon_namespace, sets_namespace, types_namespace
