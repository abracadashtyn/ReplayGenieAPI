from flask import request
from flask_restx import Namespace, fields, Resource
from sqlalchemy.exc import SQLAlchemyError

from app.api.v1 import api_v1
from app.api.v1.errors import APIError, error_response
from app.api.v1.pagination import pagination_model, paginate_query
from app.models import PokemonType

poke_type_ns = Namespace('Types', description='Endpoints related to pokemon types')
api_v1.add_namespace(poke_type_ns, path='/types')

pokemon_type_model = api_v1.model('PokemonType', {
    'id': fields.Integer(example=1),
    'name': fields.String(example="Bug"),
    'image_url': fields.String(example="https://arcvgc.com/static/images/types/bug.png"),
})
pokemon_type_list_response = api_v1.model('PokemonTypeListResponse', {
    'success': fields.Boolean(example=True),
    'data': fields.List(fields.Nested(pokemon_type_model)),
    'pagination': fields.Nested(pagination_model)
})
"""Fetch a list of all pokemon types"""
@poke_type_ns.route('/')
class PokemonTypeList(Resource):
    @poke_type_ns.doc('list_pokemon_types')
    @poke_type_ns.param('page', description='Page number', type='integer', default=1)
    @poke_type_ns.param('limit', description='Items per page', type='integer', default=50)
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
            response, data = paginate_query(query, page, limit)
            return response
        except SQLAlchemyError as e:
            raise APIError(f'Error querying database for pokemon types: {e}', code='DB_ERROR', status=500)


"""Fetch a list of all pokemon tera types"""
@poke_type_ns.route('/tera')
class PokemonTeraTypeList(Resource):
    @poke_type_ns.doc('list_pokemon_tera_types')
    @poke_type_ns.param('page', description='Page number', type='integer', default=1)
    @poke_type_ns.param('limit', description='Items per page', type='integer', default=50)
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
            response, data = paginate_query(query, page, limit)
            # re-define data as original would have been constructed for is_tera=False and will give incorrect image URLS
            response['data'] = [x.to_dict(is_tera=True) for x in data]
            return response
        except SQLAlchemyError as e:
            raise APIError(f'Error querying database for pokemon types: {e}', code='DB_ERROR', status=500)
