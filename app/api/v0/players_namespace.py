from flask import request
from flask_restx import Namespace, fields, Resource
from sqlalchemy import func, case
from sqlalchemy.exc import SQLAlchemyError

from app import db
from app.api.v0.pagination import pagination_model, paginate_query
from app.api.v0 import api_v0, error_response
from app.models import Player, PlayerMatchPokemon, PlayerMatch, Match, Pokemon

players_ns = Namespace('Players', description='Endpoints related to pokemon showdown player accounts')
api_v0.add_namespace(players_ns, path='/players')

"""Fetches a list of all players"""
player_model = api_v0.model('Player', {
    'id': fields.Integer,
    'name': fields.String
})
player_list_response = api_v0.model('PlayerListResponse', {
    'success': fields.Boolean,
    'data': fields.List(fields.Nested(player_model)),
    'pagination': fields.Nested(pagination_model)
})
@players_ns.route('/')
class PlayerListRoute(Resource):
    @players_ns.doc('list_players')
    @players_ns.param('page', 'Page number', type='integer', default=1)
    @players_ns.param('limit', 'Items per page', type='integer', default=50)
    @players_ns.param(name='name', description='username (full or partial) to filter results by', type='string')
    @players_ns.response(500, 'Internal server error', error_response)
    @players_ns.marshal_with(player_list_response, code=200)
    def get(self):
        page = request.args.get('page', 1, type=int)
        limit = request.args.get('limit', 50, type=int)
        query = Player.query.order_by(Player.name)
        if 'name' in request.args:
            search_string = request.args['name']
            if '%' not in search_string:
                search_string = f"%{search_string}%"
            query = query.filter(Player.name.like(search_string))
        try:
            return paginate_query(query, page, limit)
        except SQLAlchemyError as e:
            api_v0.abort(500, f'Error querying database for formats: {e}')\


player_match_detail = api_v0.model('PlayerMatchDetail', {
    'id': fields.Integer,
    'rating': fields.Integer,
})
pokemon_usage_detail = api_v0.model('PokemonUsageDetail', {
    'id': fields.Integer,
    'name': fields.String,
    'usage_count': fields.Integer,
    'image_url': fields.String,
})
player_detail = api_v0.inherit('PlayerDetail', player_model, {
    'match_count': fields.Integer,
    'win_count': fields.Integer,
    'top_rated_match': fields.Nested(player_match_detail),
    'most_recent_rated_match': fields.Nested(player_match_detail),
    'most_used_pokemon': fields.List(fields.Nested(pokemon_usage_detail))
})
player_response = api_v0.model('PlayerResponse', {
    'success': fields.Boolean,
    'data': fields.Nested(player_detail),
})
@players_ns.route('/<int:player_id>')
class PlayerRoute(Resource):
    @players_ns.doc('get_player')
    @players_ns.response(404, 'Player not found')
    @players_ns.marshal_with(player_response)
    def get(self, player_id):
        player_record = Player.query.get_or_404(player_id)
        counts = db.session\
            .query(
                func.count(PlayerMatch.id).label('total_matches'),
                func.sum(case((PlayerMatch.won_match == True, 1), else_=0)).label('wins'))\
            .filter(PlayerMatch.player_id == player_id)\
            .first()
        response_data = {
            'id': player_record.id,
            'name': player_record.name,
            'match_count': counts[0],
            'win_count': counts[1],
        }

        base_match_query = db.session\
            .query(Match.id, Match.rating)\
            .join(PlayerMatch)\
            .filter(PlayerMatch.player_id == player_id)\
            .filter(Match.rating != None)

        top_rating = base_match_query.order_by(Match.rating.desc()).first()
        most_recent_rating = base_match_query.order_by(Match.upload_time.desc()).first()
        if top_rating is not None:
            response_data['top_rated_match']= {
                'id': top_rating[0],
                'rating': top_rating[1]
            }
        if most_recent_rating is not None:
            response_data['most_recent_rated_match']= {
                'id': most_recent_rating[0],
                'rating': most_recent_rating[1]
            }

        pokemon_records = db.session\
            .query(
                case(
                    (Pokemon.is_cosmetic_only == True, Pokemon.base_species_id),
                    else_=Pokemon.id
                ).label("pokemon_id"),
                func.count(PlayerMatchPokemon.pokemon_id).label('usage_count'))\
            .join(PlayerMatchPokemon, PlayerMatchPokemon.pokemon_id == Pokemon.id)\
            .join(PlayerMatch)\
            .filter(PlayerMatch.player_id == player_record.id)\
            .group_by(
                case(
                    (Pokemon.is_cosmetic_only == True, Pokemon.base_species_id),
                    else_=Pokemon.id
                ))\
            .order_by(func.count(PlayerMatchPokemon.pokemon_id).desc())\
            .limit(6).all()

        response_data['most_used_pokemon'] = []
        for pokemon_record in pokemon_records:
            name = Pokemon.query.get(pokemon_record[0]).name
            response_data['most_used_pokemon'].append({
                'id': pokemon_record[0],
                'name': name,
                'usage_count': pokemon_record[1],
                'image_url': Pokemon.image_url_from_name(name),
            })

        response = {
            'success': True,
            'data': response_data
        }

        return response