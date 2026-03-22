import logging

import click
import requests
from flask import current_app

from app import redis_cache
from app.tasks import bp


@bp.cli.group()
def cacheops():
    pass

def delete_keys(keys):
    logging.basicConfig(level=logging.INFO)
    if keys:
        redis_cache.delete(*keys)
        logging.info(f"Cleared {len(keys)} cached entries")
    else:
        logging.info("Cache already empty")

@cacheops.command('clear-all')
def clear():
    delete_keys(redis_cache.keys(f"*"))

@cacheops.command('clear-pokemon')
def clear_pokemon():
    delete_keys(redis_cache.keys(f"pokemon_stats:*:*"))

@cacheops.command('clear-format')
def clear_pokemon():
    delete_keys(redis_cache.keys(f"format_stats:*:*"))

@cacheops.command('warm')
@click.option('--format_id', '-f', type=int)
def warm(format_id):
    logging.basicConfig(level=logging.INFO)

    format_url = f"{current_app.config['BASE_URL']}/api/v0/formats/{format_id}"
    logging.info(f"Calling {format_url} to warm format cache")
    try:
        format_detail = requests.get(format_url)
        if format_detail.status_code == 200:
            format_detail = format_detail.json()
            for pokemon in format_detail['data']['top_pokemon']:
                pokemon_url = f"{current_app.config['BASE_URL']}/api/v0/pokemon/{pokemon['id']}?format_id={format_id}"
                logging.info(f"Calling {pokemon_url} to warm cache for pokemon {pokemon['name']}")
                pokemon_detail = requests.get(pokemon_url)
                if pokemon_detail.status_code != 200:
                    logging.error(f"Error warming cache for pokemon {pokemon['name']}: {pokemon_detail.status_code}")
        else:
            logging.error(f"Error warming cache for format {format_id}: {format_detail.status_code}: {format_detail.text}")
    except Exception as e:
        logging.error(f"error warming cache: {e}")