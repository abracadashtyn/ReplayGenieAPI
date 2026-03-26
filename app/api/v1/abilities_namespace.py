from flask import request
from flask_restx import Namespace, fields, Resource
from sqlalchemy.exc import SQLAlchemyError

from app.api.v1.errors import APIError, error_response
from app.api.v1.pagination import pagination_model, paginate_query
from app.api.v1 import api_v1
from app.models import Ability

abilities_ns = Namespace('Abilities', description='Endpoints related to pokemon abilities.')
api_v1.add_namespace(abilities_ns, path='/abilities')


ability_model = api_v1.model('Ability', {
    'id': fields.Integer(example=1),
    'name': fields.String(example="Overgrow"),
})
ability_list_response = api_v1.model('AbilityListResponse', {
    'success': fields.Boolean(example=True),
    'data': fields.List(fields.Nested(ability_model)),
    'pagination': fields.Nested(pagination_model)
})

"""Fetches a list of all abilities"""
@abilities_ns.route('/')
class AbilityList(Resource):
    @abilities_ns.doc('list_abilities')
    @abilities_ns.param(name='page', description='Page number', type='integer', default=1)
    @abilities_ns.param(name='limit', description='Items per page', type='integer', default=50)
    @abilities_ns.param(name='name', description='Name of ability (full or partial) to filter results by', type='string')
    @abilities_ns.response(500, 'Internal server error', error_response)
    @abilities_ns.marshal_with(ability_list_response, code=200)
    def get(self):
        page = request.args.get('page', 1, type=int)
        limit = request.args.get('limit', 50, type=int)
        query = Ability.query.order_by(Ability.name)
        if 'name' in request.args:
            search_string = request.args['name']
            if '%' not in search_string:
                search_string = f"%{search_string}%"
            query = query.filter(Ability.name.like(search_string))

        try:
            response, data = paginate_query(query, page, limit)
            return response
        except SQLAlchemyError as e:
            raise APIError(f'Error querying database for abilities: {e}', code='DB_ERROR', status=500)
