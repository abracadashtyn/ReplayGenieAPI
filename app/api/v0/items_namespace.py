from flask import request
from flask_restx import Namespace, fields, Resource
from sqlalchemy.exc import SQLAlchemyError

from app.api.PaginationUtils import PaginationUtils
from app.api.v0 import api, pagination_model, error_response
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
            return PaginationUtils.paginate_query(query, page, limit)
        except SQLAlchemyError as e:
            api.abort(500, f'Error querying database for items: {e}')

"""Fetches a specific item by id
item_detail_model = api.inherit('ItemDetail', item_model, {
    'match_ids': fields.List(fields.Integer, description='List of matches where this item was used')
})
item_detail_response = api.model('ItemDetailResponse', {
    'success': fields.Boolean,
    'data': fields.List(fields.Nested(item_detail_model))
})
@items_ns.route('/<int:item_id>')
class ItemDetail(Resource):
    @items_ns.doc('get_item')
    @items_ns.response(404, 'Item not found', error_response)
    @items_ns.response(500, 'Internal server error', error_response)
    @items_ns.marshal_with(item_detail_response, code=200)
    def get(self, item_id):
        try:
            item_record = Item.query.filter_by(id=item_id).first()
        except SQLAlchemyError as e:
            # Handle database errors specifically
            api.abort(500, f'Error querying database for item with ID {item_id}: {e}')

        if not item_record:
            api.abort(404, f'Item with ID {item_id} not found')

        response = {
            'success': True,
            'data': item_record.to_dict()
        }
        response['data']['match_ids'] = list(set([x.player_match.match_id for x in item_record.pmp_records]))
        return response"""


# TODO create

# TODO update

# TODO delete
