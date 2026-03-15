import logging
import os
import re
import time

import requests
from flask import current_app

from app import db
from app.exceptions import AlreadyExistsException
from app.models import Match, Format, Player, PlayerMatch, Pokemon, PokemonType, PlayerMatchPokemon, Item, Ability, Move


class ShowdownMatchParser:
    def __init__(self, match_record, wait, local=False):
        # match record can be constructed from showdown json using the class method below, or it can be passed in directly
        self.match_record = match_record

        # if true, delay so as to not hammer showdown api
        if wait:
            logging.info(f"Waiting {current_app.config['REQUEST_DELAY']} seconds to call showdown api")
            time.sleep(current_app.config['REQUEST_DELAY'])

        # fetch the detailed log data for this particular match and save for later operations
        if local:
            file_path = os.path.join(os.getcwd(), 'app', 'static', 'test_data',
                                     f'{self.match_record.format.name}-{self.match_record.showdown_id}.txt')
            with open(file_path, 'r', encoding='utf-8') as f:
                log_string = f.read()
        else:
            replay_log_url = f"https://replay.pokemonshowdown.com/{self.match_record.format.name}-{self.match_record.showdown_id}.log"
            replay_log_response = requests.get(replay_log_url)
            if replay_log_response.status_code != 200:
                raise Exception(f"Something went wrong with web request: {replay_log_url}")
            log_string = replay_log_response.text

        self.log_lines = log_string.splitlines()


    @classmethod
    def construct_from_json(cls, match_json, format, wait, throw_if_exists=True, local=False):
        id_strings = match_json['id'].split("-")
        if len(id_strings) != 2:
            raise Exception(f"unable to parse match format {match_json['id']}")
        try:
            showdown_id = int(id_strings[1])
        except ValueError:
            raise Exception(f"Match ID {id_strings[1]} is not numeric; unsure how to handle. ")

        match_record = Match.query.filter_by(showdown_id=showdown_id).first()
        if match_record is None:
            match_record = Match()
            match_record.showdown_id = showdown_id
            match_record.upload_time = match_json["uploadtime"]
            match_record.rating = match_json["rating"]
            match_record.private = match_json["private"]
            match_record.format = format
            db.session.add(match_record)
            db.session.commit()
        else:
            if throw_if_exists:
                raise AlreadyExistsException(f"Match ID {match_json['id']} already exists")

        return cls(match_record, wait, local)


    def clean_and_split_line(self, line):
        return line.lstrip('|').rstrip('|').split('|')

    def camel_case_to_spaced(self, string):
        # Inserts a space before any capital letter that is not at the start of the string
        return re.sub(r'(?<!^)([A-Z])', r' \1', string)

    def parse_log_details(self, local=False):
        self.parse_sequence_in_set()
        self.parse_players()
        self.parse_pokemon()

    def parse_sequence_in_set(self):
        bestof_line = None
        for line in self.log_lines:
            if 'bestof' in line:
                bestof_line = line
                break
        game_number = re.search("Game ([0-9])", bestof_line)
        if not game_number or game_number.group(1) == "":
            logging.error(f"Not able to parse game number from '{bestof_line}'")
            self.match_record.position_in_set = None
        else:
            self.match_record.position_in_set = int(game_number.group(1))


    def parse_players(self):
        player1_record, player2_record = None, None
        players = [x for x in self.log_lines if x.startswith("|player|")]
        if len(players) > 2:
            players = players[:2]
        elif len(players) < 2:
            raise Exception(f"Did not find enough lines defining players in match; not sure how to parse\n{players}")

        for player_info in players:
            player_info_chunks = self.clean_and_split_line(player_info)
            if player_info_chunks[1].lower() == "p1":
                player1_record = Player.get_or_create(player_info_chunks[2])
            elif player_info_chunks[1].lower() == "p2":
                player2_record = Player.get_or_create(player_info_chunks[2])
            else:
                raise Exception(f"Was not able to parse player position for line {player_info}")

        # ensure record for both players were populated from the above logic
        if player1_record is None or player2_record is None:
            raise Exception(f"Could not parse player positions from log info {players}")

        # create a PlayerMatch record for each player (added as class param for use when parsing pokemon later)
        self.player_1_match_record = PlayerMatch.get_or_create(player1_record.id, self.match_record.id)
        self.player_2_match_record = PlayerMatch.get_or_create(player2_record.id, self.match_record.id)

        # determine who won the match and update each PlayerMatchRecord accordingly
        winner_lines = [x for x in self.log_lines if x.startswith('|win|')]
        if len(winner_lines) > 1:
            raise Exception(f"Found too many lines ({len(winner_lines)}) defining winner: {winner_lines}")
        elif len(winner_lines) < 1:
            raise Exception(f"Could not find any lines with info on winner; please check data and try again. ")

        winner = self.clean_and_split_line(winner_lines[0])[1]

        if winner.lower() == player1_record.name.lower():
            self.player_1_match_record.won_match = True
            self.player_2_match_record.won_match = False
        elif winner.lower() == player2_record.name.lower():
            self.player_1_match_record.won_match = False
            self.player_2_match_record.won_match = True
        else:
            raise Exception(f"Winner of match {winner} does not match either player name "
                            f"({player1_record.name} or {player2_record.name})")
        db.session.commit()

    def parse_pokemon(self):
        teams = [x for x in self.log_lines if x.startswith("|showteam|")]
        if len(teams) != 2:
            raise Exception(f"There should be two 'showteam' records, one for each player, but , but {len(teams)} were "
                            f"found in the log data.")

        for team in teams:
            team_info = re.search('\|showteam\|(p[1,2])\|(.*)', team)
            if team_info.group(1) == 'p1':
                pm_record_id = self.player_1_match_record.id    #p1_match_record_id
            elif team_info.group(1) == 'p2':
                pm_record_id = self.player_2_match_record.id    #p2_match_record_id
            else:
                raise Exception(f"Not able to determine which player team record belongs to. Please check data format.")

            for pokemon_data in team_info.group(2).split(']'):
                '''
                will always be of format <pokemon_name>||<item>|<ability>|<moveset>|||<gender>|||<level>|,,,,,<tera_type>
                when split on |, 
                    [0]='<pokemon_name>'
                    [1]=''
                    [2]='<item>'
                    [3]='<ability>'
                    [4]='<moveset>'
                    [5]=''
                    [6]=''
                    [7]='<gender>'
                    [8]=''
                    [9]=''
                    [10]='<level>'
                    [11]=',,,,,<tera_type>]'

                I'm unsure if the blank fields will ever be populated, or if that's simply formatting.
                TODO no documentation on this - dig through the code to find out? 
                for now raise an exception if any one of these fields is non-null to manually check the data
                '''
                pkmn_info = [x for x in pokemon_data.split('|')]

                if len(pkmn_info) != 12:
                    raise Exception(f"did not parse the expected 12 fields for pokemon team member: {pkmn_info}")

                if any(True for x in [1, 5, 6, 8, 9] if pkmn_info[x] != ""):
                    raise Exception(f"One of the pokemon match info fields expected to be empty is not: {pkmn_info}")

                # name field
                pokemon_record = Pokemon.query.filter_by(name=pkmn_info[0]).first()

                # if this is a new pokemon record, we also need to add its types from the last field in the log.
                # in theory we should never hit this
                if pokemon_record is None:
                    pokemon_record = Pokemon(name=pkmn_info[0])
                    print("THIS IS A PREVIOUSLY UNSEEN POKEMON!! check if this works ")
                    db.session.add(pokemon_record)
                    db.session.commit()
                    types = [x for x in pkmn_info[-1].split(',') if x != ""]
                    for type in types:
                        pokemon_record.types.append(PokemonType.get_or_create(type))
                    db.session.commit()

                pmp_record = PlayerMatchPokemon.get_or_create(pm_record_id, pokemon_record.id)

                # [2] = item the pokemon is holding
                if pkmn_info[2] != "":
                    pmp_record.item = Item.get_or_create(self.camel_case_to_spaced(pkmn_info[2]))

                # [3] = ability
                if pkmn_info[3] != "":
                    pmp_record.ability = Ability.get_or_create(self.camel_case_to_spaced(pkmn_info[3]))

                # [4] = moveset. Should always be present so raise exception if this field is blank.
                if pkmn_info[4] == "":
                    raise Exception(f"Moveset is null, which should not happen!")

                moves = pkmn_info[4].split(',')
                move_ids = []
                for move in moves:
                    move_record = Move.get_or_create(self.camel_case_to_spaced(move))
                    move_ids.append(move_record.id)

                pmp_record.move_1_id = move_ids[0] if len(move_ids) >= 1 else None
                pmp_record.move_2_id = move_ids[1] if len(move_ids) >= 2 else None
                pmp_record.move_3_id = move_ids[2] if len(move_ids) >= 3 else None
                pmp_record.move_4_id = move_ids[3] if len(move_ids) >= 4 else None


                # [11]=',,,,,<tera_type>]'
                if pkmn_info[11] != "":
                    tera_type_name = pkmn_info[11].lstrip(',').rstrip(']')
                    tera_type_record = PokemonType.query.filter(PokemonType.name == tera_type_name).first()

                    # all pokemon types are already in table and rarely change. If a tera type is found that does not
                    # already exist in the db, it's more likely the formatting of the log has changed than that this is
                    # actually a new pokemon type. Raise an exception in this case/
                    if tera_type_record is None:
                        raise Exception(f"Could not find tera type '{tera_type_name}'")

                    pmp_record.tera_type = tera_type_record

                db.session.commit()