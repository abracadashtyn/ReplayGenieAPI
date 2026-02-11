import json

from flask import request
from flask_restx import Namespace, fields, Resource
from sqlalchemy.exc import SQLAlchemyError

from app.api.PaginationUtils import PaginationUtils
from app.api.v0 import bp, api, pagination_model, error_response
from app.api.v0.types_namespace import pokemon_type_model
from app.models import Pokemon, PokemonType

pokemon_ns = Namespace('Pokemon')
api.add_namespace(pokemon_ns, path='/pokemon')


"""Fetch a list of all Pokemon"""
pokemon_base_species_model = api.model('PokemonReference', {
    'id': fields.Integer,
    'name': fields.String,
    'pokedex_number': fields.Integer,
    'image_url': fields.String,
})
pokemon_model = api.model('PokemonModel', {
    'id': fields.Integer,
    'pokedex_number': fields.Integer,
    'name': fields.String,
    'tier': fields.String,
    'types': fields.List(fields.Nested(pokemon_type_model)),
    'image_url': fields.String,
    'base_species': fields.Nested(pokemon_base_species_model, allow_null=True,
                                  description='Base form if this is a variant (e.g., Alolan forms)')
})
pokemon_list_response = api.model('PokemonListResponse', {
    'success': fields.Boolean,
    'data': fields.List(fields.Nested(pokemon_model)),
    'pagination': fields.Nested(pagination_model)
})
@pokemon_ns.route('/')
class PokemonList(Resource):
    @pokemon_ns.doc('list_pokemon')
    @pokemon_ns.param('page', 'Page number', type='integer', default=1)
    @pokemon_ns.param('limit', 'Items per page', type='integer', default=50)
    @pokemon_ns.param('type_ids', 'Comma separated list of type IDs to filter pokemon on',type='string')
    @pokemon_ns.param('pokedex_number', 'Pokedex number to filter pokemon on', type='integer')
    @pokemon_ns.param(name='name', description='Name of pokemon (full or partial) to filter results by', type='string')
    @pokemon_ns.response(500, 'Internal server error', error_response)
    @pokemon_ns.marshal_with(pokemon_list_response, code=200)
    def get(self):
        page = request.args.get('page', 1, type=int)
        limit = request.args.get('limit', 50, type=int)
        query = Pokemon.query.filter(Pokemon.is_cosmetic_only is False).order_by(Pokemon.pokedex_number, Pokemon.name)

        if 'type_ids' in request.args:
            try:
                type_ids = [int(id.strip()) for id in request.args.get('type_ids').split(',')]
            except ValueError:
                api.abort(400, 'Invalid type_ids')
            query = query.filter(Pokemon.types.any(PokemonType.id.in_(type_ids)))

        if 'pokedex_number' in request.args:
            pokedex_number = request.args.get('pokedex_number', type=int)
            query = query.filter(Pokemon.pokedex_number == pokedex_number)

        if 'name' in request.args:
            search_string = request.args['name']
            if '%' not in search_string:
                search_string = f"%{search_string}%"
            query = query.filter(Pokemon.name.like(search_string))

        try:
            return PaginationUtils.paginate_query(query, page, limit)

        except SQLAlchemyError as e:
            api.abort(500, f'Error querying database for pokemon types: {e}')



"""Fetch details on on particular pokemon by ID"""
pokemon_form_model = api.model('PokemonForm', {
    'id': fields.Integer,
    'pokedex_number': fields.Integer,
    'name': fields.String,
    'tier': fields.String,
    'types': fields.List(fields.Nested(pokemon_type_model)),
    'is_cosmetic_only': fields.Boolean(),
    'image_url': fields.String,
})
pokemon_detail_model = api.inherit('PokemonDetail', pokemon_model, {
    'forms': fields.List(fields.Nested(pokemon_form_model)),
})
pokemon_detail_response = api.model('PokemonDetailResponse', {
    'success': fields.Boolean,
    'data': fields.Nested(pokemon_detail_model)
})
@pokemon_ns.route('/<int:pokemon_id>')
class PokemonDetail(Resource):
    @pokemon_ns.doc('get_pokemon')
    @pokemon_ns.response(404, 'Pokemon not found', error_response)
    @pokemon_ns.response(500, 'Internal server error', error_response)
    @pokemon_ns.marshal_with(pokemon_detail_response, code=200)
    def get(self, pokemon_id):
        try:
            pokemon_record = Pokemon.query.filter_by(id=pokemon_id).first()
        except SQLAlchemyError as e:
            # Handle database errors specifically
            api.abort(500, f'Error querying database for pokemon type with ID {pokemon_id}: {e}')

        if not pokemon_record:
            api.abort(404, f'Pokemon with ID {pokemon_id} not found')

        response = {
            'success': True,
            'data': pokemon_record.to_dict()
        }

        # check if this pokemon has any forms, and if so, add to response
        forms = Pokemon.query.filter(Pokemon.base_species_id == pokemon_record.id).all()
        if len(forms) > 0:
            response['data']['forms'] = []
            for form in forms:
                form_dict = form.to_dict()
                if form_dict['is_cosmetic_only']:
                    form_dict.pop('types')
                response['data']['forms'].append(form_dict)

        print(json.dumps(response, indent=4))
        return response




