import logging
import os

import click
from sqlalchemy import delete

from app import db
from app.tasks import bp
from app.models import PlayerMatchPokemon, PlayerMatch, Match
from app.tasks.showdown_match_parser import ShowdownMatchParser


@bp.cli.group()
def dbops():
    pass

@dbops.command('clear-matches')
def clear_matches():
    PlayerMatchPokemon.query.delete()
    PlayerMatch.query.delete()
    Match.query.delete()
    db.session.commit()

@dbops.command('delete-match')
@click.option('--id', '-i', 'match_id', type=int, required=True)
def delete_match(match_id):
    match = Match.query.get(match_id)
    db.session.delete(match)
    db.session.commit()


@dbops.command('reprocess-matches')
@click.option('--ids', '-i', help='Comma-separated list of IDs')
@click.option('--wait', '-w', is_flag=True, default=True,
              help='whether to wait REQUEST_DELAY seconds before calling showdown API (to not hammer it or get rate limited)')
def reprocess_matches(ids, wait):
    logging.basicConfig(level=logging.INFO)
    if ids:
        id_list = [int(x.strip()) for x in ids.split(',')]

    for id in id_list:
        match = Match.query.get(id)
        if match:
            logging.info(f"Processing match with id {match.id}, '{match.format.name}-{match.showdown_id}'")
            match_parser = ShowdownMatchParser(match, wait)
            match_parser.parse_log_details()