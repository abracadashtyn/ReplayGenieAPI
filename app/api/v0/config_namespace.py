import logging

from flask import current_app
from flask_restx import Namespace, fields, Resource
from sqlalchemy.exc import SQLAlchemyError

from app.api.v0 import api, error_response
from app.models import Format

config_ns = Namespace('Config', description='Configuration endpoints for use in the various front-end environments')
api.add_namespace(config_ns, path='/config')


config_response = api.model('ConfigResponse', {
    'success': fields.Boolean,
    'data': fields.Nested(api.model('Config', {
        'current_format': fields.Nested(api.model('CurrentFormat', {
            'id': fields.Integer,
            'name': fields.String,
            'formatted_name': fields.String,
        })),
        'min_android_version': fields.Integer,
        'min_ios_version': fields.Integer,
        'min_web_version': fields.Integer,
        'min_catalog_version': fields.Integer,
    }))
})
@config_ns.route('/')
class Config(Resource):
    @config_ns.doc('config')
    @config_ns.response(500, 'Internal server error', error_response)
    @config_ns.marshal_with(config_response, code=200)
    def get(self):
        try:
            format = Format.query.get(current_app.config['CURRENT_FORMAT_ID'])
        except SQLAlchemyError as e:
            logging.error(f"Error querying database for current format name: {e}")
            api.abort(500, f'Error fetching current config parameters.')

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