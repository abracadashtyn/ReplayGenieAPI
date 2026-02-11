from flask import request
from flask_restx import Namespace, fields, Resource
from sqlalchemy.exc import SQLAlchemyError

from app.api.PaginationUtils import PaginationUtils
from app.api.v0 import api, pagination_model, error_response
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
            return PaginationUtils.paginate_query(query, page, limit)
        except SQLAlchemyError as e:
            api.abort(500, f'Error querying database for pokemon types: {e}')


"""fetch details on one specific pokemon type"""
pokemon_type_detail_model = api.inherit('PokemonTypeDetail', pokemon_type_model, {
    'pokemon_ids': fields.List(fields.Integer, description='List of Pokemon IDs with this type')
})
pokemon_type_detail_response = api.model('PokemonTypeDetailResponse', {
    'success': fields.Boolean,
    'data': fields.Nested(pokemon_type_detail_model)
})
@poke_type_ns.route('/<int:type_id>')
class PokemonTypeDetail(Resource):
    @poke_type_ns.doc('get_pokemon_type', description='Get details of one specific pokemon type, and a list of pokemon that are of that type.')
    @poke_type_ns.response(404, 'Pokemon type not found', error_response)
    @poke_type_ns.response(500, 'Internal server error', error_response)
    @poke_type_ns.marshal_with(pokemon_type_detail_response, code=200)
    def get(self, type_id):
        try:
            type_record = PokemonType.query.filter_by(id=type_id).first()
        except SQLAlchemyError as e:
            # Handle database errors specifically
            print(f"Error querying database for pokemon type with ID {type_id}: {e}")
            api.abort(500, f'Error querying database for pokemon type with ID {type_id}: {e}')

        if not type_record:
            api.abort(404, f'Pokemon type with ID {type_id} not found')

        response = {
            'success': True,
            'data': type_record.to_dict()
        }
        response['data']['pokemon_ids'] = [x.id for x in type_record.pokemon]
        return response
