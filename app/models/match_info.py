from datetime import datetime
import logging
import sqlalchemy as sa
import sqlalchemy.orm as so
from typing import Optional, List
from app import db

class Format(db.Model):
    __tablename__ = 'formats'
    id: so.Mapped[int] = so.mapped_column(primary_key=True)
    name: so.Mapped[str] = so.mapped_column(sa.String(100))
    formatted_name: so.Mapped[Optional[str]] = so.mapped_column(sa.String(100))

    matches: so.Mapped[List['Match']] = so.relationship(back_populates='format')

    def __repr__(self):
        return f"<Format id:{self.id}, name:{self.name}>"

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'formatted_name': self.formatted_name,
        }

    @classmethod
    def get_or_create(cls, name: str):
        format_record = cls.query.filter_by(name=name).first()
        if format_record is None:
            format_record = cls(name=name)
            db.session.add(format_record)
            db.session.commit()
        return format_record


class Match(db.Model):
    __tablename__ = 'matches'
    id: so.Mapped[int] = so.mapped_column(autoincrement=True, primary_key=True)
    showdown_id: so.Mapped[int] = so.mapped_column(sa.BigInteger)
    upload_time: so.Mapped[int] = so.mapped_column()
    rating: so.Mapped[Optional[int]] = so.mapped_column()
    private: so.Mapped[bool] = so.mapped_column()

    set_id: so.Mapped[Optional[int]] = so.mapped_column(index=True)
    position_in_set: so.Mapped[Optional[int]] = so.mapped_column()    # e.g. 2nd match out of 3 would have value 2 here

    format_id: so.Mapped[int] = so.mapped_column(sa.Integer, sa.ForeignKey(Format.id))
    format: so.Mapped[Format] = so.relationship(back_populates='matches')

    players: so.Mapped[List['PlayerMatch']] = so.relationship('PlayerMatch', back_populates='match', cascade='all, delete-orphan')

    def __repr__(self):
        return f"<Match id:{self.id}, showdown_id:{self.format.name}-{self.showdown_id}>"

    def to_dict(self):
        return {
            'id': self.id,
            'showdown_id': self.get_showdown_url_string(),
            'upload_time': (datetime.fromtimestamp(self.upload_time).isoformat()),
            'rating': self.rating,
            'private': self.private,
            # todo add set information once populated
            'format': self.format.to_dict(),
        }

    def get_showdown_url_string(self):
        return f"{self.format.name}-{self.showdown_id}"