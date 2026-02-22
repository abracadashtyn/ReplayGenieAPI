import logging
import os

import sqlalchemy as sa
import sqlalchemy.orm as so
from typing import Optional, List
from flask import Blueprint, current_app, url_for
from sqlalchemy import func

from app import db
from app.utils import format_name_to_image_file

pokemon_to_type = sa.Table(
    'pokemon_to_type',
    db.metadata,
    sa.Column('pokemon_id', sa.Integer, sa.ForeignKey('pokemon.id'), primary_key=True),
    sa.Column('type_id', sa.Integer, sa.ForeignKey('pokemon_types.id'), primary_key=True))

class PokemonType(db.Model):
    __tablename__ = 'pokemon_types'
    id: so.Mapped[int] = so.mapped_column(autoincrement=True, primary_key=True)
    name: so.Mapped[str] = so.mapped_column(sa.String(25))
    pokemon: so.Mapped[List['Pokemon']] = so.relationship(secondary=pokemon_to_type, back_populates='types')

    def __repr__(self):
        return f"<{self.name} type, id:{self.id}>"

    def to_dict(self, is_tera=False):
        if is_tera:
            return {
                'id': self.id,
                'name': self.name,
                'image_url': self.get_tera_image_url()
            }

        return {
            'id': self.id,
            'name': self.name,
            'image_url': self.get_image_url()
        }

    def get_image_url(self):
        return url_for(endpoint='static',
                filename=f'images/types/{format_name_to_image_file(self.name)}',
                _external=True)

    def get_tera_image_url(self):
        return url_for(endpoint='static',
                filename=f'images/tera/{format_name_to_image_file(self.name)}',
                _external=True)

    @classmethod
    def get_or_create(cls, name: str):
        record = cls.query.filter_by(name=name).first()
        if record is None:
            record = cls(name=name)
            db.session.add(record)
            db.session.commit()
            logging.info(f"Returning newly created record {record}")
        else:
            logging.info(f"Returning existing record {record}")
        return record


class Pokemon(db.Model):
    __tablename__ = 'pokemon'
    id: so.Mapped[int] = so.mapped_column(autoincrement=True, primary_key=True)
    pokedex_number: so.Mapped[Optional[int]] = so.mapped_column()
    name: so.Mapped[str] = so.mapped_column(sa.String(100))
    tier: so.Mapped[Optional[str]] = so.mapped_column(sa.String(100))
    is_nonstandard: so.Mapped[Optional[str]] = so.mapped_column(sa.String(100))
    base_species_id: so.Mapped[Optional[int]] = so.mapped_column(sa.Integer, sa.ForeignKey('pokemon.id'))
    base_species = so.relationship('Pokemon', remote_side=[id], backref='forms')
    is_cosmetic_only: so.Mapped[Optional[bool]] = so.mapped_column(sa.Boolean, default=False)

    types: so.Mapped[List[PokemonType]] = so.relationship(secondary=pokemon_to_type, back_populates='pokemon')

    player_matches: so.Mapped[List['PlayerMatchPokemon']] = so.relationship(back_populates='pokemon')

    def __repr__(self):
        return f"<Pokemon id:{self.id}, name:{self.name}>"

    def to_dict(self):
        pkmn_dict = {
            'id': self.id,
            'pokedex_number': self.pokedex_number,
            'name': self.name,
            'tier': self.tier,
            'is_nonstandard': self.is_nonstandard,
            'types': [x.to_dict() for x in self.types],
            'is_cosmetic_only': self.is_cosmetic_only,
            'image_url': self.get_image_url()
        }
        if self.base_species_id is not None:
            pkmn_dict['base_species'] = {
                'name': self.base_species.name,
                'id': self.base_species.id
            }
        return pkmn_dict

    def get_image_url(self):
        # TODO add logic to return image for parent if child image does not exist
        return url_for(endpoint='static',
                filename=f'images/pokemon/{format_name_to_image_file(self.name)}',
                _external=True)


    @classmethod
    def get_or_create(cls,name: str, pokedex_number:int=None):
        name_no_spaces = name.replace(' ', '')
        record = cls.query.filter(func.replace(cls.name, ' ', '') == name_no_spaces).first()
        if record is None:
            record = cls(name=name, pokedex_number=pokedex_number)
            db.session.add(record)
            db.session.commit()
            logging.info(f"Returning newly created record {record}")
        else:
            logging.info(f"Returning existing record {record}")
        return record


class Item(db.Model):
    __tablename__ = 'items'
    id: so.Mapped[int] = so.mapped_column(autoincrement=True, primary_key=True)
    name: so.Mapped[str] = so.mapped_column(sa.String(50))
    pmp_records: so.Mapped[List['PlayerMatchPokemon']] = so.relationship(back_populates='item')

    def __repr__(self):
        return f"<Item id:{self.id}, name:{self.name}>"

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'image_url': url_for(endpoint='static',
                     filename=f'images/items/{format_name_to_image_file(self.name)}',
                     _external=True)
        }

    @classmethod
    def get_or_create(cls, name: str):
        name_no_spaces = name.replace(' ', '')
        record = cls.query.filter(func.replace(cls.name, ' ', '') == name_no_spaces).first()
        if record is None:
            record = cls(name=name)
            db.session.add(record)
            db.session.commit()
            logging.info(f"Returning newly created record {record}")
        else:
            logging.info(f"Returning existing record {record}")
        return record


class Ability(db.Model):
    __tablename__ = 'abilities'
    id: so.Mapped[int] = so.mapped_column(autoincrement=True, primary_key=True)
    name: so.Mapped[str] = so.mapped_column(sa.String(50))

    def __repr__(self):
        return f"<Ability id:{self.id}, name:{self.name}>"

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name
        }

    @classmethod
    def get_or_create(cls, name: str):
        name_no_spaces = name.replace(' ', '')
        record = cls.query.filter(func.replace(cls.name, ' ', '') == name_no_spaces).first()
        if record is None:
            record = cls(name=name)
            db.session.add(record)
            db.session.commit()
            logging.info(f"Returning newly created record {record}")
        else:
            logging.info(f"Returning existing record {record}")
        return record

class Move(db.Model):
    __tablename__ = 'moves'
    id: so.Mapped[int] = so.mapped_column(autoincrement=True, primary_key=True)
    name: so.Mapped[str] = so.mapped_column(sa.String(50))

    def __repr__(self):
        return f"<Move id:{self.id}, name:{self.name}>"

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name
        }

    @classmethod
    def get_or_create(cls, name: str):
        name_no_spaces = name.replace(' ', '')
        record = cls.query.filter(func.replace(cls.name, ' ', '') == name_no_spaces).first()
        if record is None:
            record = cls(name=name)
            db.session.add(record)
            db.session.commit()
            logging.info(f"Returning newly created record {record}")
        else:
            logging.info(f"Returning existing record {record}")
        return record

