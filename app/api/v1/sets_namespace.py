from flask import request, current_app
from flask_restx import Namespace, fields, Resource
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.sql.functions import count, func

from app import db
from app.api.v1 import api_v1
from app.api.v1.errors import APIError, error_response, NotFoundError
from app.api.v1.formats_namespace import format_model
from app.api.v1.matches_namespace import default_match_limit, pokemon_instance_model
from app.api.v1.pagination import pagination_model, paginate_query
from app.api.v1.players_namespace import player_model
from app.models import Match, Format

sets_ns = Namespace('Sets',
                    description='Operations related to sets (groupings of n matches as described by the format, n=3 in all existing formats)')
api_v1.add_namespace(sets_ns, path='/sets')
default_set_limit = 20

set_match_model = api_v1.model('SetMatchModel', {
    'position_in_set': fields.Integer(example=1),
    'id': fields.Integer(example=456),
    'showdown_id': fields.String(example="gen9vgc2026regibo3-2565555555"),
    'upload_time': fields.DateTime(example="2026-01-01T17:30:00"),
    'rating': fields.Integer(example=None),
    'private': fields.Boolean(example=True),
    'winner_id': fields.Integer(example=400),
})
base_set_model = api_v1.model('BaseSetModel', {
    'id': fields.Integer(example=456),
    'max_rating': fields.Integer(example=1500),
    'match_count': fields.Integer(example=3),
    'format': fields.Nested(format_model),
    'matches': fields.List(fields.Nested(set_match_model)),
})
set_player_model = api_v1.inherit('SetPlayerModel', player_model, {
    'win_count': fields.Integer(example=2),
})
set_model = api_v1.inherit('SetModel', base_set_model, {
    'players': fields.List(fields.Nested(set_player_model)),
})
set_list_response = api_v1.model('SetListResponse', {
    'success': fields.Boolean(example=True),
    'data': fields.List(fields.Nested(set_model)),
    'pagination': fields.Nested(pagination_model)
})
"""Get a list of all sets for a given format"""
@sets_ns.route('/')
class SetList(Resource):
    @sets_ns.doc('list_sets')
    @sets_ns.param('page', description='Page number', type='integer', default=1)
    @sets_ns.param('limit', description='Items per page', type='integer', default=default_set_limit)
    @sets_ns.param('format_id', description='Format ID', type='integer')
    @sets_ns.param('rated_only', description='If true, returns only sets with at least one rated match.',
                   type='boolean', default=False)
    @sets_ns.param('complete_only', description='Includes only sets that have all three matches present',
                   type='boolean', default=False)
    @sets_ns.param('order_by', description='Sort results by time (newest to oldest) or best rating in set '
                               '(highest to lowest)', type='string', enum=['time', 'rating'], default='time')
    @sets_ns.response(500, 'Internal server error', error_response)
    @sets_ns.marshal_with(set_list_response, code=200)
    def get(self):
        page = request.args.get('page', 1, type=int)
        limit = request.args.get('limit', default_match_limit, type=int)

        query = db.session.query(
            Match.set_id,
            func.max(Match.rating).label('max_rating'),
            func.count(Match.id).label('match_count'),
        ).group_by(Match.set_id)

        if 'format_id' in request.args:
            format_id = request.args.get('format_id', type=int)
            query = query.filter(Match.format_id == format_id)
            format_data = Format.query.get(format_id)
        else:
            query = query.filter(Match.format_id == current_app.config['CURRENT_FORMAT_ID'])
            format_data = Format.query.get(current_app.config['CURRENT_FORMAT_ID'])

        if 'rated_only' in request.args and request.args.get('rated_only') == 'true':
            query = query.having(count(Match.rating) > 0)

        if 'complete_only' in request.args and request.args.get('complete_only') == 'true':
            query = query.having(func.count(Match.id) == 3)

        if 'order_by' in request.args and request.args.get('order_by') == 'rating':
            query = query.order_by(func.max(Match.rating).desc())
        else:
            query = query.order_by(func.max(Match.upload_time).desc())

        try:
            response_json, query_results = paginate_query(query, page, limit)
            for set_record in query_results:
                set_dict = {
                    'id': set_record.set_id,
                    'max_rating': set_record.max_rating,
                    'match_count': set_record.match_count,
                    'format': format_data.to_dict(),
                    'matches': [],
                    'players': []
                }
                match_records = Match.query.filter_by(set_id=set_record.set_id).order_by(Match.position_in_set).all()
                player_dict = {}
                for match_record in match_records:
                    match_dict = match_record.to_dict()
                    for player_match in match_record.players:
                        if player_match.player.id not in player_dict:
                            player_dict[player_match.player.id] = {
                                'id': player_match.player.id,
                                'name': player_match.player.name,
                                'win_count': 0
                            }
                        if player_match.won_match is True:
                            player_dict[player_match.player.id]['win_count'] += 1
                            match_dict['winner_id'] = player_match.player.id
                    set_dict['matches'].append(match_dict)
                set_dict['players'] = [x for x in player_dict.values()]
                response_json['data'].append(set_dict)
            return response_json

        except SQLAlchemyError as e:
            raise APIError(f'error querying database for set list: {e}', code='DB_ERROR', status=500)


player_match_detail_model = api_v1.inherit("PlayerSetDetails", set_player_model, {
    'team': fields.List(fields.Nested(pokemon_instance_model)),
})
set_detail_model = api_v1.inherit('SetDetailModel', base_set_model, {
    'players': fields.List(fields.Nested(player_match_detail_model)),
})
set_detail_response = api_v1.model('SetDetailResponse', {
    'success': fields.Boolean(example=True),
    'data': fields.List(fields.Nested(set_detail_model))
})
""" Fetches details for a specific set """
@sets_ns.route('/<int:set_id>')
class SetDetail(Resource):
    @sets_ns.doc('get_details')
    @sets_ns.response(404, 'Set not found', error_response)
    @sets_ns.response(500, 'Internal server error', error_response)
    @sets_ns.marshal_with(set_detail_response, code=200)
    def get(self, set_id):
        try:
            match_records = Match.query.filter_by(set_id=set_id).all()
        except SQLAlchemyError as e:
            raise APIError(f'Error querying database for set with ID {set_id}: {e}', code='DB_ERROR', status=500)

        if not match_records:
            raise NotFoundError(f'Matches with set ID {set_id} not found')

        response = {
            'success': True,
            'data': {
                'id': set_id,
                'max_rating': None,
                'match_count': len(match_records),
                'format': match_records[0].format.to_dict(),
                'matches': [],
                'players': [],
            }
        }
        player_dict = {}
        for match_record in match_records:
            match_dict = match_record.to_dict()
            for player_match in match_record.players:
                if player_match.player.id not in player_dict:
                    # if this is the first time we've seen the player, also construct their team records
                    player_dict[player_match.player.id] = {
                        'id': player_match.player.id,
                        'name': player_match.player.name,
                        'win_count': 0,
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
                    }
                if player_match.won_match is True:
                    player_dict[player_match.player.id]['win_count'] += 1
                    match_dict['winner_id'] = player_match.player.id
            response['data']['matches'].append(match_dict)

        response['data']['players'] = [x for x in player_dict.values()]
        return response
