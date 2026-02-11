from flask import Blueprint

bp = Blueprint('tasks', __name__, cli_group=None)

from app.tasks import scrape_matches, scrape_pokemon_data, dbops
