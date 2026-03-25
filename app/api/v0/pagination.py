from flask_restx import fields
from app.api.v0 import api


pagination_model = api.model('Pagination', {
    'page': fields.Integer,
    'items_per_page': fields.Integer,
    'total_items': fields.Integer,
    'total_pages': fields.Integer
})

def paginate_query(query, page, limit):
    paginated_results = query.paginate(page=page, per_page=limit, error_out=False)
    data = {
        'success': True,
        'data': [x.to_dict() for x in paginated_results.items],
        'pagination': {
            'page': page,
            'items_per_page': limit,
            'total_pages': paginated_results.pages,
            'total_items': paginated_results.total
        }
    }
    return data

