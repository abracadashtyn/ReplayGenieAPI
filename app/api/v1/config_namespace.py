from flask import current_app
from flask_restx import Namespace, Resource, fields
from sqlalchemy.exc import SQLAlchemyError

from app.api.v1 import api_v1
from app.api.v1.errors import APIError, error_response
from app.models import Format

config_ns = Namespace('Config', description='Configuration endpoints for use in the various front-end environments')
api_v1.add_namespace(config_ns, path='/config')

config_response = api_v1.model('ConfigResponse', {
    'success': fields.Boolean(example=True),
    'data': fields.Nested(api_v1.model('Config', {
        'current_format': fields.Nested(api_v1.model('CurrentFormat', {
            'id': fields.Integer(example=2),
            'name': fields.String(example="gen9vgc2026regibo3"),
            'formatted_name': fields.String(example="[Gen 9] VGC 2026 Reg I (Bo3)"),
        })),
        'min_android_version': fields.Integer(example=1),
        'min_ios_version': fields.Integer(example=1),
        'min_web_version': fields.Integer(example=1),
        'min_catalog_version': fields.Integer(example=1),
    }))
})
"""Fetches the current configuration for the app"""
@config_ns.route('/')
class ConfigV1(Resource):
    @config_ns.doc('config')
    @config_ns.response(500, 'Internal server error', error_response)
    @config_ns.marshal_with(config_response, code=200)
    def get(self):
        try:
            format = Format.query.get(current_app.config['CURRENT_FORMAT_ID'])
        except SQLAlchemyError as e:
            raise APIError(f'Error querying database for format when construction config: {e}',
                           code='DB_ERROR', status=500)

        return {
            'success': True,
            'data': {
                'current_format': {
                    'id': current_app.config['CURRENT_FORMAT_ID'],
                    'name': format.name,
                    'formatted_name': format.formatted_name,
                },
                'min_android_version': current_app.config['MIN_ANDROID_VERSION'],
                'min_ios_version': current_app.config['MIN_IOS_VERSION'],
                'min_web_version': current_app.config['MIN_WEB_VERSION'],
                'min_catalog_version': current_app.config['MIN_CATALOG_VERSION'],
            }
        }
