import json
import logging

from flask import request
from flask_restx import Namespace, fields, Resource
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError

from app import db, redis_cache
from app.api.PaginationUtils import PaginationUtils
from app.api.v0 import api, pagination_model, error_response
from app.api.v0.pokemon_namespace import teammate_frequency_model
from app.models import Format, Match, PlayerMatchPokemon, PlayerMatch, Pokemon

format_ns = Namespace('Formats', description='Endpoints related to game format, as specified by showdown API.')
api.add_namespace(format_ns, path='/formats')

"""Fetches a list of all formats"""
format_model = api.model('Format', {
    'id': fields.Integer,
    'name': fields.String,
    'formatted_name': fields.String,
})
format_list_response = api.model('FormatListResponse', {
    'success': fields.Boolean,
    'data': fields.List(fields.Nested(format_model)),
    'pagination': fields.Nested(pagination_model)
})
@format_ns.route('/')
class FormatList(Resource):
    @format_ns.doc('list_formats')
    @format_ns.param('page', 'Page number', type='integer', default=1)
    @format_ns.param('limit', 'Items per page', type='integer', default=50)
    @format_ns.response(500, 'Internal server error', error_response)
    @format_ns.marshal_with(format_list_response, code=200)
    def get(self):
        page = request.args.get('page', 1, type=int)
        limit = request.args.get('limit', 50, type=int)
        query = Format.query.order_by(Format.name)
        try:
            return PaginationUtils.paginate_query(query, page, limit)
        except SQLAlchemyError as e:
            api.abort(500, f'Error querying database for formats: {e}')


format_detail_model = api.inherit('FormatDetailModel', format_model, {
    'match_count': fields.Integer,
    'team_count': fields.Integer,
    'top_pokemon': fields.List(fields.Nested(teammate_frequency_model)),
})
format_detail_response = api.model('FormatDetailResponse', {
    'success': fields.Boolean,
    'data': fields.List(fields.Nested(format_model))
})
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
        cache_key = f"format_stats:{format_id}:{top_pokemon_count}"
        cached_response = redis_cache.get(cache_key)
        if cached_response is not None:
            cached_response = json.loads(cached_response)
            if cached_response['success'] is True:
                logging.info(f"Serving FormatDetail response for format id {format_id} from cache.")
                return cached_response

        # if no cached response found, recalculate
        format = Format.query.get(format_id)
        if format is None:
            api.abort(404, 'Format not found')

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
            PlayerMatchPokemon.pokemon_id,
            func.count('*').label('pokemon_count')
        ).select_from(
            PlayerMatchPokemon
        ).join(
            PlayerMatch, PlayerMatchPokemon.player_match_id == PlayerMatch.id
        ).join(
            Match, PlayerMatch.match_id == Match.id
        ).filter(
            Match.format_id == format_id,
        ).group_by(
            PlayerMatchPokemon.pokemon_id,
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

