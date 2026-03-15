import logging
import sqlalchemy as sa
import sqlalchemy.orm as so
from typing import Optional, List
from app import db
from app.models.pokemon_info import Pokemon, Ability, Item, PokemonType


# defines the many-to-many relationship between the Players and Matches tables.
class PlayerMatch(db.Model):
    __tablename__ = 'player_matches'
    id: so.Mapped[int] = so.mapped_column(autoincrement=True, primary_key=True)

    player_id: so.Mapped[int] = so.mapped_column(sa.Integer, sa.ForeignKey('players.id'), index=True)
    player = so.relationship('Player', back_populates='matches')

    match_id: so.Mapped[int] = so.mapped_column(sa.Integer, sa.ForeignKey('matches.id'), index=True)
    match = so.relationship('Match', back_populates='players')

    pokemon: so.Mapped[List['PlayerMatchPokemon']] = so.relationship(back_populates='player_match', passive_deletes=True)

    won_match: so.Mapped[Optional[bool]] = so.mapped_column()

    def __repr__(self):
        return (f"<PlayerMatch match:{self.match.get_showdown_url_string()} (id {self.match_id}), "
                f"player:{self.player.name} (id {self.player_id})>")

    def to_dict(self):
        return {
            'match_id': self.match_id,
            'player_id': self.player_id,
            'won_match': self.won_match,
        }

    @classmethod
    def get_or_create(cls, player_id: int, match_id: int):
        record = cls.query.filter_by(player_id=player_id, match_id=match_id).first()
        if record is None:
            record = cls(player_id=player_id, match_id=match_id)
            db.session.add(record)
            db.session.commit()
        return record

# defines the many-to-many relationship between the PlayerMatch table above and the Pokemon table
class PlayerMatchPokemon(db.Model):
    __tablename__ = 'pm_pokemon'
    id: so.Mapped[int] = so.mapped_column(autoincrement=True, primary_key=True)

    player_match_id: so.Mapped[int] = so.mapped_column(sa.Integer, sa.ForeignKey('player_matches.id'), index=True)
    player_match: so.Mapped[PlayerMatch] = so.relationship(back_populates='pokemon')

    pokemon_id: so.Mapped[int] = so.mapped_column(sa.Integer, sa.ForeignKey('pokemon.id'), index=True)
    pokemon: so.Mapped[Pokemon] = so.relationship(Pokemon, back_populates='player_matches')

    ability_id: so.Mapped[Optional[int]] = so.mapped_column(sa.Integer, sa.ForeignKey('abilities.id'))
    ability: so.Mapped[Optional[Ability]] = so.relationship(Ability)

    item_id: so.Mapped[Optional[int]] = so.mapped_column(sa.Integer, sa.ForeignKey('items.id'))
    item: so.Mapped[Optional[Item]] = so.relationship(Item)

    tera_type_id: so.Mapped[Optional[int]] = so.mapped_column(sa.Integer, sa.ForeignKey('pokemon_types.id'))
    tera_type: so.Mapped[Optional[PokemonType]] = so.relationship(PokemonType)

    move_1_id: so.Mapped[Optional[int]] = so.mapped_column(sa.Integer, sa.ForeignKey('moves.id'), index=True)
    move_1: so.Mapped[Optional['Move']] = so.relationship('Move', foreign_keys=[move_1_id])
    move_2_id: so.Mapped[Optional[int]] = so.mapped_column(sa.Integer, sa.ForeignKey('moves.id'), index=True)
    move_2: so.Mapped[Optional['Move']] = so.relationship('Move', foreign_keys=[move_2_id])
    move_3_id: so.Mapped[Optional[int]] = so.mapped_column(sa.Integer, sa.ForeignKey('moves.id'), index=True)
    move_3: so.Mapped[Optional['Move']] = so.relationship('Move', foreign_keys=[move_3_id])
    move_4_id: so.Mapped[Optional[int]] = so.mapped_column(sa.Integer, sa.ForeignKey('moves.id'), index=True)
    move_4: so.Mapped[Optional['Move']] = so.relationship('Move', foreign_keys=[move_4_id])

    def __repr__(self):
        return (f"<PlayerMatchPokemon id {self.id}, match:{self.player_match.match.get_showdown_url_string()} (id {self.player_match.match_id}), "
                f"player:{self.player_match.player.name} (id {self.player_match.player_id})>")

    def to_dict(self):
        return {
            'id': self.id,
            'player_match_id': self.player_match.match_id,
            'pokemon_id': self.pokemon_id,
            'ability_id': self.ability_id,
            'item_id': self.item_id,
            'tera_type_id': self.tera_type_id,
            'move_ids': [y.to_dict() for y in (self.move_1, self.move_2, self.move_3, self.move_4)],
        }

    @classmethod
    def get_or_create(cls, player_match_id: int, pokemon_id: int):
        record = cls.query.filter_by(player_match_id=player_match_id, pokemon_id=pokemon_id).first()
        if record is None:
            record = cls(player_match_id=player_match_id, pokemon_id=pokemon_id)
            db.session.add(record)
            db.session.commit()
        return record
