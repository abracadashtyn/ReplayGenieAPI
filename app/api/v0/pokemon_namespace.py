import time
import uuid
from collections import Counter

from flask import request, current_app
from flask_restx import Namespace, fields, Resource
from sqlalchemy import func, union_all, distinct, text
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
teammate_frequency_model = api.inherit('TeammateFrequency', pokemon_base_species_model, {
    'count': fields.Integer,
})
pokemon_detail_model = api.inherit('PokemonDetail', pokemon_model, {
    'forms': fields.List(fields.Nested(pokemon_form_model)),
    'match_count': fields.Integer,
    'match_percent': fields.Float,
    'team_count': fields.Integer,
    'team_percent': fields.Float,
    'top_items': fields.List(fields.Nested(item_frequency_model)),
    'top_tera_types': fields.List(fields.Nested(tera_type_frequency_model)),
    'top_moves': fields.List(fields.Nested(move_frequency_model)),
    'top_abilities': fields.List(fields.Nested(ability_frequency_model)),
    'top_teammates': fields.List(fields.Nested(teammate_frequency_model)),
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

        # create temporary table to pre-filter out only the relevant player_match_pokemon records for this format and
        # pokemon. Required as mysql was not materializing cte and queries were lagging.
        start_time = time.perf_counter()
        table_name = f"temp_filtered_pmp_{uuid.uuid4().hex[:8]}"
        db.session.execute(text(f"""
            CREATE TEMPORARY TABLE {table_name} AS
            SELECT 
                pmp.id,
                pmp.player_match_id,
                pmp.ability_id,
                pmp.item_id,
                pmp.tera_type_id,
                pmp.move_1_id,
                pmp.move_2_id,
                pmp.move_3_id,
                pmp.move_4_id
            FROM pm_pokemon pmp
            JOIN player_matches pm ON pmp.player_match_id = pm.id
            JOIN matches m ON pm.match_id = m.id
            WHERE m.format_id = :format_id AND pmp.pokemon_id = :pokemon_id
        """), {'format_id': format_id, 'pokemon_id': pokemon_id})
        end_time = time.perf_counter()
        print(f"temp table construction took {end_time - start_time} seconds")

        # find number of matches this mon appears in on at least one team
        start_time = time.perf_counter()
        match_count = db.session.execute(text(f"""
            SELECT
                COUNT(DISTINCT pm.match_id)
            FROM 
                {table_name} as pmp
            JOIN 
                player_matches as pm on pmp.player_match_id = pm.id
        """)).scalar()
        response['data']['match_count'] = match_count
        total_matches = Match.query.filter_by(format_id=format_id).count()
        percent_used = match_count / total_matches * 100
        response['data']['match_percent'] = percent_used
        end_time = time.perf_counter()
        print(f"match count took {end_time - start_time} seconds")

        # find count and percentage of teams this mon is used in
        start_time = time.perf_counter()
        team_count= db.session.execute(text(f"""
            SELECT 
                count(distinct pmp.player_match_id) 
            FROM
                {table_name} as pmp
        """)).scalar()
        response['data']['team_count'] = team_count
        team_percent = team_count / (total_matches * 2) * 100
        response['data']['team_percent'] = team_percent
        end_time = time.perf_counter()
        print(f"team count took {end_time - start_time} seconds")

        # aggregate the top 6 most common items used
        start_time = time.perf_counter()
        most_common_items = db.session.execute(text(f"""
            SELECT 
                i.id,
                i.name,
                count(*) as item_count
            FROM
                {table_name} as pmp
            JOIN
                items as i on pmp.item_id = i.id
            GROUP BY
                i.id,
                i.name
            ORDER BY
                item_count DESC
            LIMIT 6 
        """)).fetchall()
        end_time = time.perf_counter()
        print(f"most_common_items query took {end_time - start_time} seconds")
        response['data']['top_items'] = []
        for item in most_common_items:
            response['data']['top_items'].append({
                'id': item[0],
                'name': item[1],
                'image_url': Item.image_url_from_name(item[1]),
                'count': item[2],
            })

        # aggregate top 6 most common tera types
        start_time = time.perf_counter()
        most_common_tera = db.session.execute(text(f"""
            SELECT 
                t.id,
                t.name,
                count(*) as tera_type_count
            FROM
                {table_name} as pmp
            JOIN
                 pokemon_types as t on pmp.tera_type_id = t.id
            GROUP BY
                t.id,
                t.name
            ORDER BY
                tera_type_count DESC
            LIMIT 6
        """)).fetchall()
        end_time = time.perf_counter()
        print(f"most common tera query took {end_time - start_time} seconds")
        response['data']['top_tera_types'] = []
        for type in most_common_tera:
            response['data']['top_tera_types'].append({
                'id': type[0],
                'name': type[1],
                'image_url': PokemonType.tera_image_url_from_name(type[1]),
                'count': type[2],
            })

        # aggregate top 6 most common abilities
        start_time = time.perf_counter()
        most_common_abilities = db.session.execute(text(f"""
            SELECT
                a.id,
                a.name,
                count(*) as ability_count
            FROM
                {table_name} as pmp
            JOIN
                abilities as a on pmp.ability_id = a.id
            GROUP BY
                a.id,
                a.name
            ORDER BY
                ability_count DESC
            LIMIT 6
        """)).fetchall()
        end_time = time.perf_counter()
        print(f"most common abilities query took {end_time - start_time} seconds")
        response['data']['top_abilities'] = []
        for ability in most_common_abilities:
            response['data']['top_abilities'].append({
                'id': ability[0],
                'name': ability[1],
                'count': ability[2],
            })

        # aggregate top 6 most common moves. Each column must be queried individually and combined in python, as the
        # temp_filtered_pmp temporary table can't be reused in the same query, and when implemented as a cte it was not
        # being materialized but rather reconstructed 4 separate times, resulting in slow query times for mons with
        # many records in the PlayerMatchPokemon table.
        start_time = time.perf_counter()
        move_1 = db.session.execute(text(f"""SELECT move_1_id, count(*) as move_count FROM {table_name} WHERE move_1_id IS NOT NULL GROUP BY move_1_id""")).fetchall()
        move_2 = db.session.execute(text(f"""SELECT move_2_id, count(*) as move_count FROM {table_name} WHERE move_2_id IS NOT NULL GROUP BY move_2_id""")).fetchall()
        move_3 = db.session.execute(text(f"""SELECT move_3_id, count(*) as move_count FROM {table_name} WHERE move_3_id IS NOT NULL GROUP BY move_3_id""")).fetchall()
        move_4 = db.session.execute(text(f"""SELECT move_4_id, count(*) as move_count FROM {table_name} WHERE move_4_id IS NOT NULL GROUP BY move_4_id""")).fetchall()
        end_time = time.perf_counter()
        print(f"most common moves queries took {end_time - start_time} seconds")
        start_time = time.perf_counter()
        most_common_moves = Counter(dict(move_1))
        most_common_moves.update(dict(move_2))
        most_common_moves.update(dict(move_3))
        most_common_moves.update(dict(move_4))
        end_time = time.perf_counter()
        print(f"constructing counter for most common moves took {end_time - start_time} seconds")
        response['data']['top_moves'] = []
        for move in most_common_moves.most_common(6):
            response['data']['top_moves'].append({
                'id': move[0],
                'name': Move.query.get(move[0]).name,
                'count': move[1],
            })

        # aggregate top 6 most common teammates
        start_time = time.perf_counter()
        most_common_teammates = db.session.execute(text(f"""
            SELECT
                pmp.pokemon_id,
                count(*) as pokemon_count
            FROM
                {table_name} as tmp
            JOIN
                pm_pokemon as pmp on pmp.player_match_id = tmp.player_match_id
            WHERE
                pmp.pokemon_id != :pokemon_id
            GROUP BY
                pmp.pokemon_id
            ORDER BY
                pokemon_count DESC
            LIMIT 6
        """), {'pokemon_id': pokemon_id}).fetchall()
        end_time = time.perf_counter()
        print(f"most common teammates queries took {end_time - start_time} seconds")
        response['data']['top_teammates'] = []
        for team in most_common_teammates:
            mon_record = Pokemon.query.get(team[0]).to_dict()
            mon_record['count'] = team[1]
            response['data']['top_teammates'].append(mon_record)

        return response




