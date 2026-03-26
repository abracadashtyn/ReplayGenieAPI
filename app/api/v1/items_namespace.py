from flask import request
from flask_restx import Namespace, fields, Resource
from sqlalchemy.exc import SQLAlchemyError

from app.api.v1 import api_v1
from app.api.v1.errors import APIError, error_response
from app.api.v1.pagination import pagination_model, paginate_query
from app.models import Item

items_ns = Namespace('Items', description='Endpoints related to items pokemon hold and use.')
api_v1.add_namespace(items_ns, path='/items')

item_model = api_v1.model('Item', {
    'id': fields.Integer(example=1),
    'name': fields.String(example="Ability Capsule"),
    'image_url': fields.String(example="https://arcvgc.com/static/images/items/abilitycapsule.png"),
})
item_list_response = api_v1.model('ItemListResponse', {
    'success': fields.Boolean(example=True),
    'data': fields.List(fields.Nested(item_model)),
    'pagination': fields.Nested(pagination_model)
})
"""Fetches a list of all items"""
@items_ns.route('/')
class ItemList(Resource):
    @items_ns.doc('list_items')
    @items_ns.param('page', description='Page number', type='integer', default=1)
    @items_ns.param('limit', description='Items per page', type='integer', default=50)
    @items_ns.param(name='name', description='Name of item (full or partial) to filter results by', type='string')
    @items_ns.response(500, 'Internal server error', error_response)
    @items_ns.marshal_with(item_list_response, code=200)
    def get(self):
        page = request.args.get('page', 1, type=int)
        limit = request.args.get('limit', 50, type=int)
        query = Item.query.order_by(Item.name)
        if 'name' in request.args:
            search_string = request.args['name']
            if '%' not in search_string:
                search_string = f"%{search_string}%"
            query = query.filter(Item.name.like(search_string))
        try:
            response, data = paginate_query(query, page, limit)
            return response
        except SQLAlchemyError as e:
            raise APIError(f'Error querying database for items: {e}', code='DB_ERROR', status=500)
