from flask import request
from flask_restx import Namespace, fields, Resource
from sqlalchemy.exc import SQLAlchemyError

from app.api.v0 import api, pagination_model, error_response
from app.api.v0.abilities_namespace import ability_model
from app.api.v0.formats_namespace import format_model
from app.api.v0.items_namespace import item_model
from app.api.v0.moves_namespace import move_model
from app.api.v0.players_namespace import player_model
from app.api.v0.pokemon_namespace import pokemon_model, pokemon_base_species_model
from app.api.v0.types_namespace import pokemon_type_model
from app.models import Match

matches_ns = Namespace('Matches')
api.add_namespace(matches_ns, path='/matches')


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
    'terra_type': fields.Nested(pokemon_type_model)
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
    @matches_ns.param('limit', 'Items per page', type='integer', default=50)
    @matches_ns.param('format_id', 'Format ID', type='integer')
    @matches_ns.response(500, 'Internal server error', error_response)
    @matches_ns.marshal_with(match_list_response, code=200)
    def get(self):
        page = request.args.get('page', 1, type=int)
        limit = request.args.get('limit', 50, type=int)

        query = Match.query.order_by(Match.upload_time.desc())
        if 'format_id' in request.args:
            format = request.args.get('format_id', type=int)
            query = query.filter(Match.format_id == format)

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
                        'pokedex_number': x.pokemon.pokedex_number,
                        'name': x.pokemon.name,
                        'terra_type': x.terra_type.to_dict() if x.terra_type else None,
                        'item': x.item.to_dict() if x.item else None,
                    } for x in player_match_record.pokemon]
                })
            response_json['data'].append(match_dict)

        return response_json



""" Fetches details for a specific match """
pokemon_instance_model = api.inherit("PokemonInstance", pokemon_model, {
    'ability': fields.Nested(ability_model),
    'item': fields.Nested(item_model),
    'terra_type': fields.Nested(pokemon_type_model),
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
                    'pokedex_number': x.pokemon.pokedex_number,
                    'name': x.pokemon.name,
                    'tier': x.pokemon.tier,
                    'types': [y.to_dict() for y in x.pokemon.types],
                    'terra_type': x.terra_type.to_dict() if x.terra_type else None,
                    'base_species': x.pokemon.base_species.to_dict() if x.pokemon.base_species else None,
                    'ability': x.ability.to_dict(),
                    'item': x.item.to_dict() if x.item else None,
                    'moves': [y.to_dict() for y in x.moves]
                } for x in player_match.pokemon]
            })
        return response

