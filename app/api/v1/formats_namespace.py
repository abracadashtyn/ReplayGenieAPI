import json
import logging

from flask import request
from flask_restx import Namespace, fields, Resource
from sqlalchemy import func, case
from sqlalchemy.exc import SQLAlchemyError

from app import db, redis_cache
from app.api.v1 import api_v1
from app.api.v1.errors import APIError, error_response, NotFoundError
from app.api.v1.pagination import pagination_model, paginate_query
from app.api.v1.pokemon_namespace import teammate_frequency_model
from app.models import Format, Match, PlayerMatchPokemon, PlayerMatch, Pokemon

format_ns = Namespace('Formats', description='Endpoints related to game format, as specified by showdown API.')
api_v1.add_namespace(format_ns, path='/formats')

format_model = api_v1.model('Format', {
    'id': fields.Integer(example=2),
    'name': fields.String(example="gen9vgc2026regibo3"),
    'formatted_name': fields.String(example="[Gen 9] VGC 2026 Reg I (Bo3)"),
})
format_list_response = api_v1.model('FormatListResponse', {
    'success': fields.Boolean(example=True),
    'data': fields.List(fields.Nested(format_model)),
    'pagination': fields.Nested(pagination_model)
})

"""Fetches a list of all formats"""
@format_ns.route('/')
class FormatList(Resource):
    @format_ns.doc('list_formats')
    @format_ns.param('page', description='Page number', type='integer', default=1)
    @format_ns.param('limit', description='Items per page', type='integer', default=50)
    @format_ns.response(500, 'Internal server error', error_response)
    @format_ns.marshal_with(format_list_response, code=200)
    def get(self):
        page = request.args.get('page', 1, type=int)
        limit = request.args.get('limit', 50, type=int)
        query = Format.query.order_by(Format.name)
        try:
            response, data = paginate_query(query, page, limit)
            return response
        except SQLAlchemyError as e:
            raise APIError(f'Error querying database for formats: {e}', code='DB_ERROR', status=500)


format_detail_model = api_v1.inherit('FormatDetailModel', format_model, {
    'match_count': fields.Integer(example=500),
    'team_count': fields.Integer(example=1000),
    'top_pokemon': fields.List(fields.Nested(teammate_frequency_model)),
})
format_detail_response = api_v1.model('FormatDetailResponse', {
    'success': fields.Boolean(example=True),
    'data': fields.List(fields.Nested(format_model))
})
"""Fetches details about a specific format, including total number of matches in the format and the top n most used 
pokemon in games of this format."""
@format_ns.route('/<int:format_id>')
class FormatDetail(Resource):
    @format_ns.doc('get_format')
    @format_ns.param('top_pokemon_count', type='integer',
                     description='The number of top pokemon to include in the response')
    @format_ns.response(404, 'Format not found', error_response)
    @format_ns.response(500, 'Internal server error', error_response)
    def get(self, format_id):
        # cache is split between format data itself and pokemon data. First, check if format data is present and if not,
        # calculate it
        format_cache_key = f"format_stats:v1:{format_id}"
        response = redis_cache.get(format_cache_key)
        if response is None:
            format = Format.query.get(format_id)
            if format is None:
                raise NotFoundError(f'Format with id {format_id} not found.')
            response = {
                'success': True,
                'data': format.to_dict()
            }
            # get total count of matches in this format
            match_count = Match.query.filter_by(format_id=format_id).count()
            response['data']['match_count'] = match_count
            response['data']['team_count'] = match_count * 2

        # now check if pokemon usage data is stored in the cache. If not, do a query to get counts of all pokemon used
        top_pokemon_cache_key = f"format_pokemon_stats:v1:{format_id}"
        top_pokemon_list = redis_cache.get(top_pokemon_cache_key)
        if top_pokemon_list is None:
            # no cached top mons, must do search again
            top_pokemon_query = db.session.query(
                case(
                    (Pokemon.is_cosmetic_only == True, Pokemon.base_species_id),
                    else_=Pokemon.id
                ).label("pokemon_id"),
                func.count('*').label('pokemon_count')
            ).select_from(
                PlayerMatchPokemon
            ).join(
                PlayerMatch, PlayerMatchPokemon.player_match_id == PlayerMatch.id
            ).join(
                Match, PlayerMatch.match_id == Match.id
            ).join(
                Pokemon, PlayerMatchPokemon.pokemon_id == Pokemon.id
            ).filter(
                Match.format_id == format_id,
            ).group_by(
                case(
                    (Pokemon.is_cosmetic_only == True, Pokemon.base_species_id),
                    else_=Pokemon.id
                ),
            ).order_by(
                func.count('*').desc()
            )
            top_pokemon_list = [(x[0], x[1]) for x in top_pokemon_query.all()]
            redis_cache.setex(top_pokemon_cache_key, 2100, json.dumps(top_pokemon_list))
            logging.info(f"Stored top pokemon list in cache with key {top_pokemon_cache_key}")
        else:
            top_pokemon_list = json.loads(top_pokemon_list)
            logging.info(f"pulled top pokemon list from cache.")

        top_pokemon_count = request.args.get('top_pokemon_count', 6, type=int)
        response['data']['top_pokemon'] = []
        for pokemon in top_pokemon_list[:top_pokemon_count]:
            pokemon_dict = Pokemon.query.get(pokemon[0]).to_dict()
            pokemon_dict['count'] = pokemon[1]
            response['data']['top_pokemon'].append(pokemon_dict)

        return response
