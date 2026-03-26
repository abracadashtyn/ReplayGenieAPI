from flask import request
from flask_restx import Namespace, fields, Resource
from sqlalchemy.exc import SQLAlchemyError

from app.api.v1 import api_v1
from app.api.v1.errors import APIError, error_response
from app.api.v1.pagination import pagination_model, paginate_query
from app.models import Move

moves_ns = Namespace('Moves', description='Endpoints related to pokemon moves.')
api_v1.add_namespace(moves_ns, path='/moves')


move_model = api_v1.model('Move', {
    'id': fields.Integer(example=1),
    'name': fields.String(example="Surging Strikes"),
})
move_list_response = api_v1.model('MoveListResponse', {
    'success': fields.Boolean(example=True),
    'data': fields.List(fields.Nested(move_model)),
    'pagination': fields.Nested(pagination_model)
})
"""Fetches a list of all moves"""
@moves_ns.route('/')
class MoveList(Resource):
    @moves_ns.doc('list_moves')
    @moves_ns.param('page', description='Page number', type='integer', default=1)
    @moves_ns.param('limit', description='Items per page', type='integer', default=50)
    @moves_ns.param(name='name', description='Name of move (full or partial) to filter results by', type='string')
    @moves_ns.response(500, 'Internal server error', error_response)
    @moves_ns.marshal_with(move_list_response, code=200)
    def get(self):
        page = request.args.get('page', 1, type=int)
        limit = request.args.get('limit', 50, type=int)
        query = Move.query.order_by(Move.name)
        if 'name' in request.args:
            search_string = request.args['name']
            if '%' not in search_string:
                search_string = f"%{search_string}%"
            query = query.filter(Move.name.like(search_string))
        try:
            response, data = paginate_query(query, page, limit)
            return response
        except SQLAlchemyError as e:
            raise APIError(f'Error querying database for moves: {e}')
