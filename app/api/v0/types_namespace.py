from flask import request
from flask_restx import Namespace, fields, Resource
from sqlalchemy.exc import SQLAlchemyError

from app.api.v0.pagination import pagination_model, paginate_query
from app.api.v0 import api, error_response
from app.models import PokemonType

poke_type_ns = Namespace('Types', description='Endpoints related to pokemon types')
api.add_namespace(poke_type_ns, path='/types')


"""Fetch a list of all pokemon types"""
pokemon_type_model = api.model('PokemonType', {
    'id': fields.Integer(required=True),
    'name': fields.String(required=True),
    'image_url': fields.String,
})
pokemon_type_list_response = api.model('PokemonTypeListResponse', {
    'success': fields.Boolean,
    'data': fields.List(fields.Nested(pokemon_type_model)),
    'pagination': fields.Nested(pagination_model)
})
@poke_type_ns.route('/')
class PokemonTypeList(Resource):
    @poke_type_ns.doc('list_pokemon_types')
    @poke_type_ns.param('page', 'Page number', type='integer', default=1)
    @poke_type_ns.param('limit', 'Items per page', type='integer', default=50)
    @poke_type_ns.param(name='name', description='Type name (full or partial) to filter results by', type='string')
    @poke_type_ns.response(500, 'Internal server error', error_response)
    @poke_type_ns.marshal_with(pokemon_type_list_response, code=200)
    def get(self):
        page = request.args.get('page', 1, type=int)
        limit = request.args.get('limit', 50, type=int)
        query = PokemonType.query.order_by(PokemonType.name)
        if 'name' in request.args:
            search_string = request.args['name']
            if '%' not in search_string:
                search_string = f"%{search_string}%"
            query = query.filter(PokemonType.name.like(search_string))
        try:
            return paginate_query(query, page, limit)
        except SQLAlchemyError as e:
            api.abort(500, f'Error querying database for pokemon types: {e}')


"""Fetch a list of all pokemon types"""
@poke_type_ns.route('/tera')
class PokemonTeraTypeList(Resource):
    @poke_type_ns.doc('list_pokemon_tera_types')
    @poke_type_ns.param('page', 'Page number', type='integer', default=1)
    @poke_type_ns.param('limit', 'Items per page', type='integer', default=50)
    @poke_type_ns.param(name='name', description='Tera type name (full or partial) to filter results by', type='string')
    @poke_type_ns.response(500, 'Internal server error', error_response)
    @poke_type_ns.marshal_with(pokemon_type_list_response, code=200)
    def get(self):
        page = request.args.get('page', 1, type=int)
        limit = request.args.get('limit', 50, type=int)
        query = PokemonType.query.order_by(PokemonType.name)
        if 'name' in request.args:
            search_string = request.args['name']
            if '%' not in search_string:
                search_string = f"%{search_string}%"
            query = query.filter(PokemonType.name.like(search_string))
        try:
            paginated_results = query.paginate(page=page, per_page=limit, error_out=False)
            data = {
                'success': True,
                'data': [x.to_dict(is_tera=True) for x in paginated_results.items],
                'pagination': {
                    'page': page,
                    'items_per_page': limit,
                    'total_pages': paginated_results.pages,
                    'total_items': paginated_results.total
                }
            }
            return data
        except SQLAlchemyError as e:
            api.abort(500, f'Error querying database for pokemon types: {e}')


