import click
import requests
from flask import current_app

from app import redis_cache
from app.tasks import bp


@bp.cli.group()
def cacheops():
    pass

def delete_keys(match_pattern):
    cursor = 0
    while True:
        cursor, keys = redis_cache.scan(cursor=cursor, match=match_pattern, count=100)
        if len(keys) > 0:
            redis_cache.delete(*keys)
        if cursor == 0:
            return

@cacheops.command('clear-all')
def clear():
    redis_cache.flushall()

@cacheops.command('clear-pokemon')
def clear_pokemon():
    delete_keys("pokemon_stats:v*:*:*")

@cacheops.command('clear-format')
def clear_format():
    delete_keys("format_stats:v*")
    delete_keys("format_pokemon_stats:v1:*")

@cacheops.command('echo-keys')
def echo_keys():
    cursor = 0
    while True:
        cursor, keys = redis_cache.scan(cursor=cursor, match="*", count=100)
        for key in keys:
            print(key)
        if cursor == 0:
            return

@cacheops.command('warm')
@click.option('--format_id', '-f', type=int)
@click.option('--api_version', '-v', type=int, default=1, help="Version of the API to warm the cache for.")
def warm(format_id, api_version):
    if format_id is None:
        format_id = current_app.config.get('CURRENT_FORMAT_ID')
    format_url = f"{current_app.config['BASE_URL']}/api/v{api_version}/formats/{format_id}?top_pokemon_count=10"
    click.echo(f"Calling {format_url} to warm format cache")
    try:
        format_detail = requests.get(format_url)
        if format_detail.status_code == 200:
            format_detail = format_detail.json()
            for pokemon in format_detail['data']['top_pokemon']:
                pokemon_url = f"{current_app.config['BASE_URL']}/api/v{api_version}/pokemon/{pokemon['id']}?format_id={format_id}"
                click.echo(f"Calling {pokemon_url} to warm cache for pokemon {pokemon['name']}")
                pokemon_detail = requests.get(pokemon_url)
                if pokemon_detail.status_code != 200:
                    click.echo(f"ERROR: web request to warm cache for pokemon {pokemon['name']} failed. "
                               f"{pokemon_detail.status_code}: {pokemon_detail.text}")
        else:
            click.echo(f"ERROR: web request to warm cache for format {format_id} failed. "
                       f"{format_detail.status_code}: {format_detail.text}")

        if api_version == 1:
            # warm cache for new endpoint 'best_previous_day' that only exists in v1
            best_prev_day_url = f"{current_app.config['BASE_URL']}/api/v{api_version}/matches/best_previous_day?format_id={format_id}"
            click.echo(f"Calling {best_prev_day_url} to warm cache for home page top 50 matches in last 24 hours")
            best_prev_response = requests.get(best_prev_day_url)
            if best_prev_response.status_code != 200:
                click.echo(f"ERROR: web request to warm cache for home page failed. "
                           f"{best_prev_response.status_code}: {best_prev_response.text} ")

    except Exception as e:
        click.echo(f"ERROR: exception thrown while warming cache: {e}")