from sqlalchemy import delete

from app import db
from app.tasks import bp
from app.models import PlayerMatchPokemon, PlayerMatch, Match, pmp_move, PokemonType


@bp.cli.group()
def dbops():
    pass

@dbops.command('clear-matches')
def clear_matches():
    db.session.execute(delete(pmp_move))
    PlayerMatchPokemon.query.delete()
    PlayerMatch.query.delete()
    Match.query.delete()
    db.session.commit()
