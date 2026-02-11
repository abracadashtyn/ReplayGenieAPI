import os

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from config.shared import Config


db = SQLAlchemy()
migrate = Migrate()

def create_app(config_class=None):
    app = Flask(__name__)

    # load configdata shared across environments
    app.config.from_object(Config)

    # Auto-detect env-specific config files  based on environment variable
    if config_class is None:
        env = os.environ.get('FLASK_ENV', 'development')
        if env == 'production':
            from config.digitalocean import DigitalOceanConfig
            config_class = DigitalOceanConfig
        else:
            from config.local import LocalConfig
            config_class = LocalConfig
    app.config.from_object(config_class)

    db.init_app(app)
    migrate.init_app(app, db)

    from app.models import bp as models_bp
    app.register_blueprint(models_bp)

    from app.tasks import bp as tasks_bp
    app.register_blueprint(tasks_bp)

    from app.api.v0 import bp as api_bp
    app.register_blueprint(api_bp)

    # make sure all static image directories exist
    os.makedirs(app.config['STATIC_IMAGES_DIR'], exist_ok=True)
    os.makedirs(app.config['POKEMON_IMAGES_DIR'], exist_ok=True)
    os.makedirs(app.config['ITEM_IMAGES_DIR'], exist_ok=True)
    os.makedirs(app.config['TYPE_IMAGES_DIR'], exist_ok=True)

    return app