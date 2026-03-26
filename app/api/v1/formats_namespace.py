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
        # try to pull from cache first
        top_pokemon_count = request.args.get('top_pokemon_count', 6, type=int)
        cache_key = f"format_stats:v1:{format_id}:{top_pokemon_count}"
        cached_response = redis_cache.get(cache_key)
        if cached_response is not None:
            cached_response = json.loads(cached_response)
            if cached_response['success'] is True:
                logging.info(f"Serving FormatDetail response for format id {format_id} from cache.")
                return cached_response

        # if no cached response found, recalculate
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

        # get the top n used mons in this format (n=param value or 6 if none is provided)
        top_mons_query = db.session.query(
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
        ).limit(
            request.args.get('top_pokemon_count', 6, type=int)
        ).all()
        response['data']['top_pokemon'] = []
        for pokemon_data in top_mons_query:
            pokemon_dict = Pokemon.query.get(pokemon_data[0]).to_dict()
            pokemon_dict['count'] = pokemon_data[1]
            response['data']['top_pokemon'].append(pokemon_dict)

        # store response in cache for faster retrieval next time. Cache duration is 35 min, but will be manually
        # invalidated by ingestion method when new data is added
        redis_cache.setex(cache_key, 2100, json.dumps(response))
        logging.info(f"Stored response in cache with key {cache_key}")

        return response
