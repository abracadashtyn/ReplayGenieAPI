from flask import request, current_app
from flask_restx import Namespace, fields, Resource

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.sql.functions import count, func

from app import db
from app.api.v0 import api, pagination_model, error_response
from app.api.v0.formats_namespace import format_model
from app.api.v0.matches_namespace import default_match_limit, pokemon_instance_model
from app.models import Match, Format

sets_ns = Namespace('Sets', description='Operations related to sets (groupings of n matches as described by the format, n=3 in all existing formats)')
api.add_namespace(sets_ns, path='/sets')
default_set_limit = 20

set_match_model = api.model('SetMatchModel', {
    'position_in_set': fields.Integer,
    'id': fields.Integer,
    'showdown_id': fields.String,
    'upload_time': fields.DateTime,
    'rating': fields.Integer,
    'private': fields.Boolean,
    'winner_id': fields.Integer,
})
base_set_model = api.model('BaseSetModel', {
    'id': fields.Integer,
    'max_rating': fields.Integer,
    'match_count': fields.Integer,
    'format': fields.Nested(format_model),
    'matches': fields.List(fields.Nested(set_match_model)),
})
set_player_model = api.model('SetPlayerModel', {
    'id': fields.Integer,
    'name': fields.String,
    'win_count': fields.Integer,
})
set_model = api.inherit('SetModel', base_set_model, {
    'players': fields.List(fields.Nested(set_player_model)),
})
set_list_response = api.model('SetListResponse', {
    'success': fields.Boolean,
    'data': fields.List(fields.Nested(set_model)),
    'pagination': fields.Nested(pagination_model)
})
@sets_ns.route('/')
class SetList(Resource):
    @sets_ns.doc('list_sets')
    @sets_ns.param('page', 'Page number', type='integer', default=1)
    @sets_ns.param('limit', 'Items per page', type='integer', default=default_set_limit)
    @sets_ns.param('format_id', 'Format ID', type='integer')
    @sets_ns.param('rated_only', 'If true, returns only sets with at least one rated match.',
                   type='boolean', default=False)
    @sets_ns.param('complete_only', 'Includes only sets that have all three matches present',
                   type='boolean', default=False)
    @sets_ns.param('order_by', 'Sort results by time (newest to oldest) or best rating in set '
                               '(highest to lowest)',type='string', enum=['time', 'rating'], default='time')
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
        for set_record in paginated_results:
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

""" Fetches details for a specific set """
player_match_detail_model = api.inherit("PlayerSetDetails", set_player_model, {
    'team': fields.List(fields.Nested(pokemon_instance_model)),
})
set_detail_model = api.inherit('SetDetailModel', base_set_model, {
    'players': fields.List(fields.Nested(player_match_detail_model)),
})
set_detail_response = api.model('SetDetailResponse', {
    'success': fields.Boolean,
    'data': fields.List(fields.Nested(set_detail_model))
})
@sets_ns.route('/<int:set_id>')
class SetDetails(Resource):
    @sets_ns.doc('get_details')
    @sets_ns.response(404, 'Set not found', error_response)
    @sets_ns.response(500, 'Internal server error', error_response)
    @sets_ns.marshal_with(set_detail_response, code=200)
    def get(self, set_id):
        try:
            match_records = Match.query.filter_by(set_id=set_id).all()
        except SQLAlchemyError as e:
            api.abort(500, f'Error querying database for set with ID {set_id}: {e}')

        if not match_records:
            api.abort(404, f'Matches with set ID {set_id} not found')

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