from flask import request, current_app
from flask_restx import Namespace, fields, Resource
from sqlalchemy import func, union_all, distinct
from sqlalchemy.exc import SQLAlchemyError

from app import db
from app.api.PaginationUtils import PaginationUtils
from app.api.v0 import bp, api, pagination_model, error_response
from app.api.v0.abilities_namespace import ability_model
from app.api.v0.items_namespace import item_model
from app.api.v0.moves_namespace import move_model
from app.api.v0.types_namespace import pokemon_type_model
from app.models import Pokemon, PokemonType, PlayerMatchPokemon, Item, PlayerMatch, Match, Move, Ability

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
    @pokemon_ns.param('exclude_illegal', 'Filters list so no pokemon from the illegal tier appear in results', type='boolean', default=True)
    @pokemon_ns.param('type_ids', 'Comma separated list of type IDs to filter pokemon on',type='string')
    @pokemon_ns.param(name='name', description='Name of pokemon (full or partial) to filter results by', type='string')
    @pokemon_ns.response(500, 'Internal server error', error_response)
    @pokemon_ns.marshal_with(pokemon_list_response, code=200)
    def get(self):
        page = request.args.get('page', 1, type=int)
        limit = request.args.get('limit', 50, type=int)
        query = Pokemon.query\
            .filter(Pokemon.is_cosmetic_only == False)\
            .order_by(Pokemon.pokedex_number, Pokemon.name)

        if 'exclude_illegal' in request.args and (request.args['exclude_illegal'] is True or request.args['exclude_illegal'].lower() == "true"):
            query = query.filter(Pokemon.tier != "Illegal")

        if 'type_ids' in request.args:
            try:
                type_ids = [int(id.strip()) for id in request.args.get('type_ids').split(',')]
            except ValueError:
                api.abort(400, 'Invalid type_ids')
            query = query.filter(Pokemon.types.any(PokemonType.id.in_(type_ids)))

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
item_frequency_model = api.inherit('ItemFrequency', item_model, {
    'count': fields.Integer,
})
tera_type_frequency_model = api.inherit('TeraTypeFrequency', pokemon_type_model, {
    'count': fields.Integer,
})
move_frequency_model = api.inherit('MoveFrequency', move_model, {
    'count': fields.Integer,
})
ability_frequency_model = api.inherit('AbilityFrequency', ability_model, {
    'count': fields.Integer,
})
pokemon_detail_model = api.inherit('PokemonDetail', pokemon_model, {
    'forms': fields.List(fields.Nested(pokemon_form_model)),
    'match_count': fields.Integer,
    'match_percent': fields.Float,
    'top_items': fields.List(fields.Nested(item_frequency_model)),
    'top_tera_types': fields.List(fields.Nested(tera_type_frequency_model)),
    'top_moves': fields.List(fields.Nested(move_frequency_model)),
    'top_abilities': fields.List(fields.Nested(ability_frequency_model)),
})
pokemon_detail_response = api.model('PokemonDetailResponse', {
    'success': fields.Boolean,
    'data': fields.Nested(pokemon_detail_model)
})
@pokemon_ns.route('/<int:pokemon_id>')
class PokemonDetail(Resource):
    @pokemon_ns.doc('get_pokemon')
    @pokemon_ns.param('format_id', 'Format ID', type='integer')
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

        # base query that filters PlayerMatchPokemon records to current format
        format_id = request.args.get('format_id', type=int) if 'format_id' in request.args \
            else current_app.config['CURRENT_FORMAT_ID']

        filtered_pmp = db.session.query(
            PlayerMatchPokemon
        ).join(
            PlayerMatch, PlayerMatchPokemon.player_match_id == PlayerMatch.id
        ).join(
            Match, PlayerMatch.match_id == Match.id
        ).filter(
            Match.format_id == format_id,
            PlayerMatchPokemon.pokemon_id == pokemon_id
        ).cte('filtered_pmp')

        # find count and percentage of matches this mon is used in
        match_count = db.session.query(
            func.count(func.distinct(PlayerMatch.match_id))
        ).select_from(
            filtered_pmp
        ).join(
            PlayerMatch, filtered_pmp.c.player_match_id == PlayerMatch.id
        ).scalar()
        print(f"match count: {match_count}")
        response['data']['match_count'] = match_count
        total_matches = Match.query.count()
        percent_used = match_count/total_matches * 100
        print(f"used in {match_count} out of {total_matches} matches ({percent_used:.2f}%)")
        response['data']['match_percent'] = percent_used

        # most common items
        most_common_items = db.session.query(
            Item.id,
            Item.name,
            func.count('*').label('item_count')
        ).join(
            filtered_pmp, filtered_pmp.c.item_id == Item.id
        ).group_by(
            Item.id,
            Item.name
        ).order_by(
            func.count('*').desc()
        ).limit(6).all()
        response['data']['top_items'] = []
        for item in most_common_items:
            response['data']['top_items'].append({
                'id': item[0],
                'name': item[1],
                'image_url': Item.image_url_from_name(item[1]),
                'count': item[2],
            })

        # most common tera types
        most_common_tera = db.session.query(
            PokemonType.id,
            PokemonType.name,
            func.count('*').label('tera_type_count')
        ).join(
            filtered_pmp, filtered_pmp.c.tera_type_id == PokemonType.id
        ).group_by(
            PokemonType.id,
            PokemonType.name
        ).order_by(
            func.count('*').desc()
        ).limit(6).all()
        response['data']['top_tera_types'] = []
        for type in most_common_tera:
            response['data']['top_tera_types'].append({
                'id': type[0],
                'name': type[1],
                'image_url': PokemonType.image_url_from_name(type[1]),
                'count': type[2],
            })

        # most common abilities
        most_common_abilities = db.session.query(
            Ability.id,
            Ability.name,
            func.count('*').label('abilities_count')
        ).join(
            filtered_pmp, filtered_pmp.c.ability_id == Ability.id
        ).group_by(
            Ability.id,
            Ability.name
        ).order_by(
            func.count('*').desc()
        ).limit(6).all()
        response['data']['top_abilities'] = []
        for ability in most_common_abilities:
            response['data']['top_abilities'].append({
                'id': ability[0],
                'name': ability[1],
                'count': ability[2],
            })

        # most common moves
        move1 = db.session.query(filtered_pmp.c.move_1_id.label('move_id')).filter(filtered_pmp.c.move_1_id.is_not(None))
        move2 = db.session.query(filtered_pmp.c.move_2_id.label('move_id')).filter(filtered_pmp.c.move_2_id.is_not(None))
        move3 = db.session.query(filtered_pmp.c.move_3_id.label('move_id')).filter(filtered_pmp.c.move_3_id.is_not(None))
        move4 = db.session.query(filtered_pmp.c.move_4_id.label('move_id')).filter(filtered_pmp.c.move_4_id.is_not(None))
        all_moves = union_all(move1, move2, move3, move4).subquery()
        most_common_moves = db.session.query(
            all_moves.c.move_id,
            func.count('*').label('move_count')
        ).group_by(
            all_moves.c.move_id
        ).order_by(
            func.count('*').desc()
        ).limit(6).all()
        response['data']['top_moves'] = []
        for move in most_common_moves:
            response['data']['top_moves'].append({
                'id': move[0],
                'name': Move.query.get(move[0]).name,
                'count': move[1],
            })

        # most common teammates

        return response




