from flask import request
from flask_restx import Namespace, fields, Resource
from sqlalchemy.exc import SQLAlchemyError

from app.api.v0.pagination import pagination_model, paginate_query
from app.api.v0 import api, error_response
from app.models import Item

items_ns = Namespace('Items', description='Endpoints related to items pokemon hold and use.')
api.add_namespace(items_ns, path='/items')


"""Fetches a list of all items"""
item_model = api.model('Item', {
    'id': fields.Integer,
    'name': fields.String,
    'image_url': fields.String,
})
item_list_response = api.model('ItemListResponse', {
    'success': fields.Boolean,
    'data': fields.List(fields.Nested(item_model)),
    'pagination': fields.Nested(pagination_model)
})
@items_ns.route('/')
class ItemList(Resource):
    @items_ns.doc('list_items')
    @items_ns.param('page', 'Page number', type='integer', default=1)
    @items_ns.param('limit', 'Items per page', type='integer', default=50)
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
            return paginate_query(query, page, limit)
        except SQLAlchemyError as e:
            api.abort(500, f'Error querying database for items: {e}')
