from flask import request, current_app
from flask_restx import Namespace, fields, Resource
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import selectinload

from app import db
from app.api.v1 import api_v1
from app.api.v1.abilities_namespace import ability_model
from app.api.v1.errors import APIError, error_response, NotFoundError, ValidationError
from app.api.v1.formats_namespace import format_model
from app.api.v1.items_namespace import item_model
from app.api.v1.moves_namespace import move_model
from app.api.v1.pagination import pagination_model
from app.api.v1.players_namespace import player_model
from app.api.v1.pokemon_namespace import pokemon_model, pokemon_base_species_model
from app.api.v1.types_namespace import pokemon_type_model
from app.models import Match, PlayerMatch, Pokemon

matches_ns = Namespace('Matches', description='Operations related to matches')
api_v1.add_namespace(matches_ns, path='/matches')
default_match_limit = 50


def format_match_data(query_results):
    data = []
    for match_record in query_results:
        match_dict = match_record.to_dict()
        match_dict['players'] = []
        for player_match_record in match_record.players:
            match_dict['players'].append({
                'id': player_match_record.player_id,
                'winner': player_match_record.won_match,
                'name': player_match_record.player.name,
                'team': [{
                    'id': x.pokemon_id,
                    'image_url': x.pokemon.get_image_url(),
                    'pokedex_number': x.pokemon.pokedex_number,
                    'name': x.pokemon.name,
                    'tera_type': x.tera_type.to_dict(is_tera=True) if x.tera_type else None,
                    'item': x.item.to_dict() if x.item else None,
                } for x in player_match_record.pokemon]
            })
        data.append(match_dict)
    return data


base_match_model = api_v1.model('BaseMatch', {
    'id': fields.Integer(example=1),
    'showdown_id': fields.String(example="gen9vgc2026regibo3-2565555555"),
    'upload_time': fields.DateTime(example="2026-01-01T17:30:00"),
    'rating': fields.Integer(example=1000),
    'private': fields.Boolean(example=False),
    'format': fields.Nested(format_model),
    'set_id': fields.String(example=205),
    'position_in_set': fields.Integer(example=3),
})
match_list_response = api_v1.model('MatchListResponse', {
    'success': fields.Boolean(example=True),
    'data': fields.List(fields.Nested(api_v1.inherit('Match', base_match_model, {
        'players': fields.List(fields.Nested(api_v1.inherit("PlayerMatchDetails", player_model, {
            'is_winner': fields.Boolean(example=True),
            'team': fields.List(fields.Nested(api_v1.inherit('BasePokemon', pokemon_base_species_model, {
                'item': fields.Nested(item_model),
                'tera_type': fields.Nested(pokemon_type_model)
            }))),
        }))),
    }))),
    'pagination': fields.Nested(pagination_model)
})
"""Fetches a list of all matches"""
@matches_ns.route('/')
class MatchList(Resource):
    @matches_ns.doc('list_matches')
    @matches_ns.param('page', description='Page number', type='integer', default=1)
    @matches_ns.param('limit', description='Items per page', type='integer', default=default_match_limit)
    @matches_ns.param('format_id', description='Format ID', type='integer')
    @matches_ns.param('rated_only', description='If true, returns only matches that are rated.', type='boolean', default=False)
    @matches_ns.param('order_by', description='Sort results by time (newest to oldest) or rating (highest to lowest)',
                      type='string', enum=['time', 'rating'], default='time')
    @matches_ns.response(500, 'Internal server error', error_response)
    @matches_ns.marshal_with(match_list_response, code=200)
    def get(self):
        page = request.args.get('page', 1, type=int)
        limit = request.args.get('limit', default_match_limit, type=int)

        query = Match.query

        if 'format_id' in request.args:
            format = request.args.get('format_id', type=int)
            query = query.filter(Match.format_id == format)
        else:
            query = query.filter(Match.format_id == current_app.config['CURRENT_FORMAT_ID'])

        if 'rated_only' in request.args and request.args.get('rated_only') == 'true':
            query = query.filter(Match.rating.is_not(None))

        if 'order_by' in request.args and request.args.get('order_by') == 'rating':
            query = query.order_by(Match.rating.desc())
        else:
            query = query.order_by(Match.upload_time.desc())

        try:
            results = query \
                .limit(limit + 1) \
                .offset((page - 1) * limit) \
                .options(selectinload(Match.players).selectinload(PlayerMatch.pokemon)) \
                .all()
            has_next = False
            if len(results) > limit:
                has_next = True
                results = results[:limit]

            response_json = {
                'success': True,
                'data': format_match_data(results),
                'pagination': {
                    'page': page,
                    'items_per_page': limit,
                    'has_next': has_next,
                }
            }
            return response_json
        except SQLAlchemyError as e:
            raise APIError(f'Error querying database for matches: {e}', code='DB_ERROR', status=500)


pokemon_instance_model = api_v1.inherit("PokemonInstance", pokemon_model, {
    'ability': fields.Nested(ability_model),
    'item': fields.Nested(item_model),
    'tera_type': fields.Nested(pokemon_type_model),
    'moves': fields.List(fields.Nested(move_model))
})
player_match_detail_model = api_v1.inherit("PlayerMatchDetails", player_model, {
    'winner': fields.Boolean(example=True),
    'team': fields.List(fields.Nested(pokemon_instance_model)),
})
match_detail_response = api_v1.model('MatchDetailResponse', {
    'success': fields.Boolean(example=True),
    'data': fields.List(fields.Nested(api_v1.inherit('MatchDetails', base_match_model, {
        'players': fields.List(fields.Nested(player_match_detail_model)),
        'set_matches': fields.List(fields.Nested(api_v1.model('SetMatchOverview', {
            'id': fields.Integer(Example=43809),
            'showdown_id': fields.String(example="gen9vgc2026regibo3-2565555555"),
            'position_in_set': fields.Integer(example=1),
        }))),
    })))
})
""" Fetches details for a specific match """
@matches_ns.route('/<int:match_id>')
class MatchDetail(Resource):
    @matches_ns.doc('get_details')
    @matches_ns.response(404, 'Match not found', error_response)
    @matches_ns.response(500, 'Internal server error', error_response)
    @matches_ns.marshal_with(match_detail_response, code=200)
    def get(self, match_id):
        match_record = None
        try:
            match_record = Match.query.filter_by(id=match_id).first()
        except SQLAlchemyError as e:
            raise APIError(f'Error querying database for match with id {match_id}: {e}',
                           code='DB_ERROR', status=500)
        if match_record is None:
            raise NotFoundError(f'Match with ID {match_id} not found')

        response = {
            'success': True,
            'data': match_record.to_dict()
        }
        response['data']['players'] = []
        for player_match in match_record.players:
            response['data']['players'].append({
                'id': player_match.player_id,
                'won_match': player_match.won_match,
                'name': player_match.player.name,
                'team': [{
                    'id': x.pokemon_id,
                    'image_url': x.pokemon.get_image_url(),
                    'pokedex_number': x.pokemon.pokedex_number,
                    'name': x.pokemon.name,
                    'tier': x.pokemon.tier,
                    'types': [y.to_dict() for y in x.pokemon.types],
                    'tera_type': x.tera_type.to_dict(is_tera=True) if x.tera_type else None,
                    'base_species': x.pokemon.base_species.to_dict() if x.pokemon.base_species else None,
                    'ability': x.ability.to_dict() if x.ability else None,
                    'item': x.item.to_dict() if x.item else None,
                    'moves': [y.to_dict() for y in (x.move_1, x.move_2, x.move_3, x.move_4) if y is not None]
                } for x in player_match.pokemon]
            })

        response['data']['set_matches'] = []
        set_matches = Match.query.filter(Match.set_id == match_record.set_id).all()
        for set_match in set_matches:
            response['data']['set_matches'].append({
                'id': set_match.id,
                'showdown_id': set_match.get_showdown_url_string(),
                'position_in_set': set_match.position_in_set,
            })
        return response


search_pokemon_request_model = api_v1.model('SearchPokemonModel', {
    'id': fields.Integer(required=True, example=1),
    'item_id': fields.Integer(example=139),
    'tera_type_id': fields.Integer(example=30),
    'ability_id': fields.Integer(example=50),
})
search_team_model = api_v1.model('SearchTeamModel', {
    'player_id': fields.Integer(example=200),
    'is_winner': fields.Boolean(example=True),
    'pokemon': fields.List(fields.Nested(search_pokemon_request_model)),
})
search_request_model = api_v1.model('SearchModel', {
    'limit': fields.Integer(example=default_match_limit),
    'page': fields.Integer(example=1),
    'format_id': fields.Integer(example=1),
    'rating': fields.Nested(api_v1.model('RatingModel', {
        'min': fields.Integer(example=1000),
        'max': fields.Integer(example=1500),
        'unrated_only': fields.Boolean(example=False),
    })),
    'pokemon': fields.List(fields.Nested(search_pokemon_request_model)),
    'team1': fields.Nested(search_team_model),
    'team2': fields.Nested(search_team_model),
    'order_by': fields.String(
        required=False,
        enum=['time', 'rating'],
        default='time',
        example='time',
        description='Sort results by time (most recent to oldest) or rating (highest first)'
    ),
    'time_range': fields.Nested(api_v1.model('TimeRangeModel', {
        'start': fields.Integer(description='Inclusive, in Unix epoch timestamp format', example=1773528580),
        'end': fields.Integer(description='Inclusive, in Unix epoch timestamp format', example=1773528820),
    })),
    'player_id': fields.Integer(example=568),
    'player_name': fields.String(description="will be superceded by user_id field if both are provided."),
    'set_id': fields.Integer(example=300)
})
"""Helper method used for all pokemon filters (at base level and within team1 and team2) in search query."""
def generate_pokemon_clauses(query_dict, pokemon_filter_list, pmp_table_alias):
    all_pokemon_or_clauses = []
    for pokemon_filter in pokemon_filter_list:
        pokemon_where_conditions = []

        ids = [pokemon_filter['id']]
        # also check if any cosmetic children have matches
        children = Pokemon.query.filter(
            Pokemon.base_species_id == pokemon_filter['id'],
            Pokemon.is_cosmetic_only == True
        ).all()
        ids += [x.id for x in children]

        if len(ids) == 1:
            pokemon_where_conditions.append(f"{pmp_table_alias}.pokemon_id={pokemon_filter['id']}")
        else:
            pokemon_where_conditions.append(f"{pmp_table_alias}.pokemon_id in ({','.join([str(x) for x in ids])})")

        if 'item_id' in pokemon_filter:
            pokemon_where_conditions.append(f"{pmp_table_alias}.item_id={pokemon_filter['item_id']}")

        if 'tera_type_id' in pokemon_filter:
            pokemon_where_conditions.append(f"{pmp_table_alias}.tera_type_id={pokemon_filter['tera_type_id']}")

        if 'ability_id' in pokemon_filter:
            pokemon_where_conditions.append(f"{pmp_table_alias}.ability_id={pokemon_filter['ability_id']}")

        all_pokemon_or_clauses.append(f"({' AND '.join(pokemon_where_conditions)})")

    if len(all_pokemon_or_clauses) == 1:
        query_dict['where'].append(all_pokemon_or_clauses[0])
    else:
        query_dict['where'].append(f"({' OR '.join(all_pokemon_or_clauses)})")
        for clause in all_pokemon_or_clauses:
            query_dict['having'].append(f"COUNT(DISTINCT CASE WHEN {clause} THEN 1 END) >= 1")
        query_dict['group_by'].append("m.id")

    return query_dict


"""Endpoint to search matches on various critera as outlined by the search_request_model."""
@matches_ns.route('/search')
class SearchMatches(Resource):
    @api_v1.expect(search_request_model, validate=True)
    @matches_ns.response(500, 'Internal server error', error_response)
    @matches_ns.marshal_with(match_list_response, code=200)
    def post(self):
        search_data = api_v1.payload
        query_dict = {
            "select": [],
            "from": [],
            "join": [],
            "where": [],
            "group_by": [],
            "having": [],
            "order_by": [],
        }
        query_dict['select'].append("DISTINCT m.id")
        query_dict['from'].append("matches as m")

        # filters on the matches table
        if 'format_id' in search_data and search_data['format_id'] != "":
            query_dict['where'].append(f"m.format_id={search_data['format_id']}")

        if 'time_range' in search_data:
            if 'start' in search_data['time_range']:
                query_dict['where'].append(f"m.upload_time >= {search_data['time_range']['start']}")
            if 'end' in search_data['time_range']:
                query_dict['where'].append(f"m.upload_time <= {search_data['time_range']['end']}")

        if 'rating' in search_data:
            if 'unrated_only' in search_data['rating'] and search_data['rating']['unrated_only'] is True:
                if 'min' in search_data['rating'] or 'max' in search_data['rating']:
                    raise ValidationError("'rating' parameters are invalid - cannot provide rating range while "
                                          "'unrated_only' parameter is set to 'true'.")

                query_dict['where'].append(f"m.rating is null")

            if 'min' in search_data['rating'] and search_data.get('rating', 'min') != None:
                query_dict['where'].append(f"m.rating >= {search_data['rating']['min']}")

            if 'max' in search_data['rating'] and search_data.get('rating', 'max') != None:
                query_dict['where'].append(f"m.rating <= {search_data['rating']['max']}")

        if 'set_id' in search_data:
            query_dict['where'].append(f"m.set_id={search_data['set_id']}")

        # team filters (mutually exclusive with player_id, player_name, and pokemon filters below)
        if 'team1' in search_data or 'team2' in search_data:
            if 'pokemon' in search_data and len(search_data['pokemon']) > 0:
                raise ValidationError("Invalid search parameters. Either provide pokemon in 'team1'/'team2' params or in"
                                  "'pokemon' param, but not both.")
            elif 'player_id' in search_data or 'player_name' in search_data:
                raise ValidationError("Invalid search paramters. If using team specification, must tie player_id to one of "
                                  "'team1' or 'team2'")

            if 'team1' in search_data:
                query_dict['join'].append(f"player_matches as pm1 on m.id=pm1.match_id")
                if 'player_id' in search_data['team1']:
                    query_dict['where'].append(f"pm1.player_id={search_data['team1']['player_id']}")
                if 'is_winner' in search_data['team1']:
                    if search_data['team1']['is_winner'] is True:
                        query_dict['where'].append(f"pm1.won_match=1")
                    else:
                        query_dict['where'].append(f"pm1.won_match=0")
                if 'pokemon' in search_data['team1'] and len(search_data['team1']['pokemon']) > 0:
                    query_dict['join'].append(f"pm_pokemon as pmp1 on pm1.id=pmp1.player_match_id")

            if 'team2' in search_data:
                query_dict['join'].append(f"player_matches as pm2 on m.id=pm2.match_id")
                if 'player_id' in search_data['team2']:
                    query_dict['where'].append(f"pm2.player_id={search_data['team2']['player_id']}")
                if 'is_winner' in search_data['team2']:
                    if search_data['team2']['is_winner'] is True:
                        query_dict['where'].append(f"pm2.won_match=1")
                    else:
                        query_dict['where'].append(f"pm2.won_match=0")
                if 'pokemon' in search_data['team2'] and len(search_data['team2']['pokemon']) > 0:
                    query_dict['join'].append(f"pm_pokemon as pmp2 on pm2.id=pmp2.player_match_id")

            if 'team1' in search_data and 'team2' in search_data:
                query_dict['where'].append(f"pm1.player_id!=pm2.player_id")

        # join to player_match to filter on player data
        if 'player_id' in search_data:
            query_dict['join'].append(f"player_matches as pm on m.id=pm.match_id")
            query_dict['where'].append(f"pm.player_id={search_data['player_id']}")

        elif 'player_name' in search_data:
            query_dict['join'].append(f"player_matches as pm on m.id=pm.match_id")
            query_dict['join'].append(f"players as p on pm.player_id=p.id")
            query_dict['where'].append(f"p.name=\"{search_data['player_name']}\"")

        # join to pm_pokemon to filter on pokemon data
        if 'pokemon' in search_data and len(search_data['pokemon']) > 0:
            # if the join clauses aren't empty, the join to player_matches must already exist. If not, add it
            if len(query_dict['join']) == 0:
                query_dict['join'].append(f"player_matches as pm on m.id=pm.match_id")
            query_dict['join'].append(f"pm_pokemon as pmp on pm.id=pmp.player_match_id")
            query_dict = generate_pokemon_clauses(query_dict, search_data['pokemon'], 'pmp')

        # set up the query to get match objects at the end; done at this point to preserve ordering
        match_obj_query = Match.query
        if 'order_by' in search_data and search_data['order_by'] == 'rating':
            match_obj_query = match_obj_query.order_by(Match.rating.desc(), Match.id.desc())
            query_dict['select'].append("m.rating")
            query_dict['order_by'].append("m.rating desc")
            query_dict['order_by'].append("m.id desc")
            if len(query_dict['group_by']) > 0:
                query_dict['group_by'].append("m.rating")

        else:
            match_obj_query = match_obj_query.order_by(Match.upload_time.desc(), Match.id.desc())
            query_dict['select'].append("m.upload_time")
            query_dict['order_by'].append("m.upload_time desc")
            query_dict['order_by'].append('m.id desc')
            if len(query_dict['group_by']) > 0:
                query_dict['group_by'].append("m.upload_time")

        query_string = f"SELECT {','.join(query_dict['select'])} FROM {','.join(query_dict['from'])}"
        if len(query_dict['join']) > 0:
            query_string += f" JOIN {' JOIN '.join(query_dict['join'])}"
        if len(query_dict['where']) > 0:
            query_string += f" WHERE {' AND '.join(query_dict['where'])}"
        if len(query_dict['group_by']) > 0:
            query_string += f" GROUP BY {', '.join(query_dict['group_by'])}"
        if len(query_dict['having']) > 0:
            query_string += f" HAVING {' AND '.join(query_dict['having'])}"
        if len(query_dict['order_by']) > 0:
            query_string += f" ORDER BY {', '.join(query_dict['order_by'])}"

        # print(f"Constructed query:\n{query_string}\n-------")

        page = search_data['page'] if 'page' in search_data else 1
        limit = search_data['limit'] if 'limit' in search_data else default_match_limit
        offset = (page - 1) * limit
        match_search_results = db.session.execute(text(query_string), {"limit": limit + 1, "offset": offset}).all()
        match_ids = [x[0] for x in match_search_results]
        # print(f"Found {len(match_ids)} match ids in original search")

        response_json = {
            'success': True,
            'data': [],
            'pagination': {
                'page': page,
                'items_per_page': limit,
                'has_next': False
            }
        }
        if len(match_ids) != 0 and len(match_ids) > limit:
            response_json['pagination']['has_next'] = True
            match_ids = match_ids[:limit]

        # once ids are obtained, load Match objects into memory with additional query
        # start_time = time.perf_counter()
        match_obj_query = match_obj_query.filter(Match.id.in_(match_ids))
        # print(f"Generated match obj query: {match_obj_query.statement.compile(compile_kwargs={"literal_binds": True})}")
        match_objs = match_obj_query.all()
        # print(f"Found {len(match_objs)} matches for object query")

        # temp check to ensure order is maintained
        '''for ind, match_record in enumerate(match_objs):
            if match_search_results[ind][0] != match_record.id:
                print(f"OUT OF ORDER! {match_search_results[ind]} vs {match_record.to_dict}")'''

        response_json['data'] = format_match_data(match_objs)
        # end_time = time.perf_counter()
        # print(f"Response time: {end_time - start_time}")
        return response_json
