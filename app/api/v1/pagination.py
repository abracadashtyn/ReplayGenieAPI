from flask_restx import fields

from app.api.v1 import api_v1

pagination_model = api_v1.model('Pagination', {
    'page': fields.Integer(example=1),
    'items_per_page': fields.Integer(example=50),
    'has_next': fields.Boolean(example=True),
})

"""Helper method to paginate sqlalchemy object queries (as opposed to plaintext queries)"""
def paginate_query(query, page, limit):
    offset = (page - 1) * limit
    results = query.limit(limit + 1).offset(offset).all()

    # if limit + 1 records exist, this means there's at least 1 more page of results. Remove the extra result and
    # indicate next page exists in response. This saves having to find all qualifying matches to get a count like
    # sqlalchemy's .paginate() method does, like implemented in api v0
    has_next = False
    if len(results) != 0 and len(results) > limit:
        has_next = True
        results = results[:limit]

    data = {
        'success': True,
        'data': [x.to_dict() for x in results],
        'pagination': {
            'page': page,
            'items_per_page': limit,
            'has_next': has_next,
        }
    }
    return data, results

