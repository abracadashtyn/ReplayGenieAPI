from flask import Blueprint
from flask_restx import Api, fields


bp = Blueprint('api', __name__, url_prefix='/api/v1')
api_v1 = Api(
    bp,
    version='1.0',
    title='ReplayGenie API',
    doc='/docs'
)

from app.api.v1 import abilities_namespace, config_namespace, formats_namespace, items_namespace, matches_namespace,\
                       moves_namespace, players_namespace, pokemon_namespace, sets_namespace, types_namespace
