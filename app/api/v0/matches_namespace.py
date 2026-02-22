import json

from flask import request, current_app
from flask_restx import Namespace, fields, Resource
from sqlalchemy.exc import SQLAlchemyError

from app import db
from app.api.v0 import api, pagination_model, error_response
from app.api.v0.abilities_namespace import ability_model
from app.api.v0.formats_namespace import format_model
from app.api.v0.items_namespace import item_model
from app.api.v0.moves_namespace import move_model
from app.api.v0.players_namespace import player_model
from app.api.v0.pokemon_namespace import pokemon_model, pokemon_base_species_model
from app.api.v0.types_namespace import pokemon_type_model
from app.models import Match, PlayerMatchPokemon, PlayerMatch

matches_ns = Namespace('Matches')
api.add_namespace(matches_ns, path='/matches')

default_match_limit = 50

def query_and_format_matches(query, page, limit):
    try:
        paginated_results = query.paginate(page=page, per_page=limit, error_out=False)
    except SQLAlchemyError as e:
        api.abort(500, f'Error querying database for matches: {e}')

    response_json = {
        'success': True,
        'data': [],
        'pagination': {
            'page': page,
            'items_per_page': limit,
            'total_pages': paginated_results.pages,
            'total_items': paginated_results.total
        }
    }
    for match_record in paginated_results:
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
        response_json['data'].append(match_dict)

    return response_json

"""Fetches a list of all matches"""
base_match_model = api.model('BaseMatch', {
    'id': fields.Integer,
    'showdown_id': fields.String,
    'upload_time': fields.DateTime,
    'rating': fields.Integer,
    'private': fields.Boolean,
    'format': fields.Nested(format_model),
})
pokemon_team_overview_model = api.inherit('BasePokemon', pokemon_base_species_model, {
    'item': fields.Nested(item_model),
    'tera_type': fields.Nested(pokemon_type_model)
})
player_match_model = api.inherit("PlayerMatchDetails", player_model, {
    'winner': fields.Boolean,
    'team': fields.List(fields.Nested(pokemon_team_overview_model)),
})
match_model = api.inherit('Match', base_match_model, {
    'players': fields.List(fields.Nested(player_match_model))
})
match_list_response = api.model('MatchListResponse', {
    'success': fields.Boolean,
    'data': fields.List(fields.Nested(match_model)),
    'pagination': fields.Nested(pagination_model)
})
@matches_ns.route('/')
class MatchList(Resource):
    @matches_ns.doc('list_matches')
    @matches_ns.param('page', 'Page number', type='integer', default=1)
    @matches_ns.param('limit', 'Items per page', type='integer', default=default_match_limit)
    @matches_ns.param('format_id', 'Format ID', default=1, type='integer')
    @matches_ns.param('rated_only', 'If true, returns only matches that are rated.', type='boolean', default=False)
    @matches_ns.param('order_by', 'Sort results by time (newest to oldest) or rating (highest to lowest)',
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
            print("Requesting rated matches only")
            query = query.filter(Match.rating.is_not(None))

        if 'order_by' in request.args and request.args.get('order_by') == 'rating':
            query = query.order_by(Match.rating.desc())
        else:
            query = query.order_by(Match.upload_time.desc())

        return query_and_format_matches(query, page, limit)



""" Fetches details for a specific match """
pokemon_instance_model = api.inherit("PokemonInstance", pokemon_model, {
    'ability': fields.Nested(ability_model),
    'item': fields.Nested(item_model),
    'tera_type': fields.Nested(pokemon_type_model),
    'moves': fields.List(fields.Nested(move_model))
})
player_match_detail_model = api.inherit("PlayerMatchDetails", player_model, {
    'winner': fields.Boolean,
    'team': fields.List(fields.Nested(pokemon_instance_model)),
})
match_detail_model = api.inherit('MatchDetails', base_match_model, {
        'players': fields.List(fields.Nested(player_match_detail_model))
})
match_detail_response = api.model('MatchDetailResponse', {
    'success': fields.Boolean,
    'data': fields.List(fields.Nested(match_detail_model))
})
@matches_ns.route('/<int:match_id>')
class MatchDetails(Resource):
    @matches_ns.doc('get_details')
    @matches_ns.response(404, 'Pokemon not found', error_response)
    @matches_ns.response(500, 'Internal server error', error_response)
    @matches_ns.marshal_with(match_detail_response, code=200)
    def get(self, match_id):
        try:
            match_record = Match.query.filter_by(id=match_id).first()
        except SQLAlchemyError as e:
            api.abort(500, f'Error querying database for match with ID {match_id}: {e}')

        if not match_record:
            api.abort(404, f'Match with ID {match_id} not found')

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
                    'ability': x.ability.to_dict(),
                    'item': x.item.to_dict() if x.item else None,
                    'moves': [y.to_dict() for y in x.moves]
                } for x in player_match.pokemon]
            })
        return response


search_pokemon_request_model = api.model('SearchPokemonModel', {
    'id': fields.Integer(required=True),
    'item_id': fields.Integer,
    'tera_type_id': fields.Integer,
})
search_request_model = api.model('SearchModel', {
    'limit': fields.Integer(example=default_match_limit),
    'page': fields.Integer(example=1),
    'format_id': fields.Integer(example=1),
    'minimum_rating': fields.Integer(example=0),
    'pokemon': fields.List(fields.Nested(search_pokemon_request_model)),
    'order_by': fields.String(
        required=False,
        enum=['time', 'rating'],
        default='time',
        example='time',
        description='Sort results by time (most recent to oldest) or rating (highest first)'
    )
})
@matches_ns.route('/search')
class Search(Resource):
    @api.expect(search_request_model, validate=True)
    @matches_ns.response(500, 'Internal server error', error_response)
    @matches_ns.marshal_with(match_list_response, code=200)
    def post(self):
        search_data = api.payload

        page = search_data['page'] if 'page' in search_data else 1
        limit = search_data['limit'] if 'limit' in search_data else default_match_limit

        query = Match.query

        if 'format_id' in search_data and search_data['format_id'] != "":
            query = query.filter(Match.format_id == search_data['format_id'])
        else:
            # TODO - better to return all formats or just currently played format?
            query = query.filter(Match.format_id == current_app.config['CURRENT_FORMAT_ID'])

        if 'minimum_rating' in search_data and search_data['minimum_rating'] != "":
            query = query.filter(Match.rating >= search_data['minimum_rating'])

        if len(search_data['pokemon']) > 0:
            pokemon_query_chunks = []
            for pokemon_filter in search_data['pokemon']:
                filter_conditions = [PlayerMatchPokemon.pokemon_id == pokemon_filter['id']]
                if 'item_id' in pokemon_filter:
                    filter_conditions.append(PlayerMatchPokemon.item_id == pokemon_filter['item_id'])
                if 'tera_type_id' in pokemon_filter:
                    filter_conditions.append(PlayerMatchPokemon.tera_type_id == pokemon_filter['tera_type_id'])
                pokemon_query_chunks.append(PlayerMatch.pokemon.any(db.and_(*filter_conditions)))
            query = query.filter(Match.players.any(db.and_(*pokemon_query_chunks)))

        if 'order_by' in search_data and search_data['order_by'] == 'rating':
            query = query.order_by(Match.rating.desc())
        else:
            query = query.order_by(Match.upload_time.desc())

        return query_and_format_matches(query, page, limit)
