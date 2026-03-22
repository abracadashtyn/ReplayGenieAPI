import json
import logging
import os
import time
import click
import requests
from flask import current_app
from sqlalchemy import literal_column, update, exists
from sqlalchemy.orm import aliased
from app import db, redis_cache
from app.exceptions import AlreadyExistsException, CustomGameException
from app.models import Format, Match, PlayerMatch, Player, PlayerMatchPokemon
from app.tasks import bp
from app.tasks.cache_operations import clear, warm
from app.tasks.showdown_match_parser import ShowdownMatchParser

list_replays_url = "https://replay.pokemonshowdown.com/search.json"


@bp.cli.group()
def showdown():
    """Commands to scrape matches from showdown urls"""
    pass

#TODO remove other scrapers once the one below is tested
@showdown.command('scrape')
@click.pass_context
@click.option('--format_id', '-f', type=int)
@click.option('--historical', '-h', is_flag=True, default=False,
              help='if present, scrapes all matches older than the oldest match currently in the database')
@click.option('--all', '-a', is_flag=True, default=False,
              help='if present, scrapes all matches, even those currently in the database')
def scrape(ctx, format_id, historical, all):
    logging.basicConfig(level=logging.INFO)

    # get the format id - default to current as specified in config if no value is provided
    format_id = current_app.config.get('CURRENT_FORMAT_ID') if format_id is None else format_id
    format = Format.query.get(format_id)
    if format is None:
        logging.error("format ID does not exist in database")
        exit(1)

    comparison_timestamp = None
    if historical:
        logging.info('Scraping historical data.')
        mode = 'historical'
        error_file_name = f'scrape-{int(time.time())}.json'
        earliest_match = Match.query.filter_by(format_id=format.id).order_by(Match.upload_time.asc()).first()
        comparison_timestamp = earliest_match.upload_time
        logging.info(f"Timestamp of earliest match is {comparison_timestamp}. Scraping matches older than this...")

    elif all:
        logging.info('Scraping everything.')
        mode = 'all'
        error_file_name = f'scrape-all-{int(time.time())}.json'
        
    else:
        # default behavior is to scrape new
        mode = 'new'
        error_file_name = f'scrape-new-{int(time.time())}.json'
        last_match = Match.query.filter_by(format_id=format.id).order_by(Match.upload_time.desc()).first()
        comparison_timestamp = last_match.upload_time
        logging.info(f"Timestamp of last match is {comparison_timestamp}. Scraping matches more recent than this...")

    error_file_path = os.path.join(os.getcwd(), 'app', 'tasks', 'errors', error_file_name)

    # query showdown api for all matches in desired format.
    params = {"format": format.name}
    if historical:
        params['before'] = comparison_timestamp

    response = requests.get(list_replays_url, params=params)
    if response.status_code != 200:
        logging.error(f"Something went wrong searching showdown: {response}")
        exit(3)

    matches_json = response.json()
    matches_added_count = 0
    while len(matches_json) > 0:
        for match_json in matches_json:
            if mode == 'new' and match_json['uploadtime'] < comparison_timestamp:
                logging.info(f"Match {match_json['id']} with timestamp {match_json['uploadtime']} is older than"
                             f" {comparison_timestamp}. Match scraping is complete. Added {matches_added_count} matches "
                             f"to database.")
                return
            else:
                logging.info(f"Processing match {match_json['id']}")
                match_parser = None
                try:
                    match_parser = ShowdownMatchParser.construct_from_json(match_json, format.id, wait=True,
                                                                           throw_if_exists=True)
                    match_parser.parse_log_details()
                    matches_added_count += 1
                except AlreadyExistsException:
                    logging.info(f"Match {match_json['id']} already exists, skipping.")
                    continue
                except CustomGameException:
                    logging.error("This is a custom game. Will delete any data populated by it and skip.")
                    if match_parser:
                        db.session.delete(match_parser.match_record)
                        db.session.commit()
                    continue
                except Exception as e:
                    # any exception thrown beyond AlreadyExistsException is a genuine processing error. log it and continue
                    logging.error(f"ERROR processing match {match_json['id']}: {e}")
                    error_json = {
                        "showdown_id": match_json['id'],
                        "error": str(e),
                        "match_json": match_json
                    }
                    with open(error_file_path, 'a', encoding='utf-8') as f:
                        f.write(json.dumps(error_json) + "\n")
                    if match_parser:
                        db.session.delete(match_parser.match_record)
                        db.session.commit()
                    continue

        # 51 is the limit of matches that can be returned by this call, so if there are 51, there might be more results
        # on the next page. Query for those.
        if len(matches_json) == 51:
            params["before"] = matches_json[-1]['uploadtime']
            logging.info(
                f"Processed all results from this page, getting more matches before timestamp {params['before']}")
            response = requests.get(list_replays_url, params=params)
            if response.status_code != 200:
                logging.error(f"Something went wrong with web request: {response}")
                exit(1)
            else:
                matches_json = response.json()
        else:
            logging.info(f"There were {len(matches_json)} matches in these results, so we've seen everything")
            matches_json = []

    # invalidate pokemon and format stats cache now that new data is present
    ctx.invoke(clear)

    # warm cache for format and most commonly used pokemon
    ctx.invoke(warm, format_id=format_id)




@showdown.command('scrape-new')
@click.option('--format_id', '-f', type=int)
@click.option('--wait', '-w', is_flag=True, default=True,
              help='whether to wait REQUEST_DELAY seconds before calling showdown API (to not hammer it or get rate limited)')
def scrape_new(format_id, wait):
    logging.basicConfig(level=logging.INFO)
    error_file_name = os.path.join(os.getcwd(), 'app', 'tasks', 'errors', f'scrape-new-{int(time.time())}.json')

    # get the format id - default to current as specified in config if no value is provided
    format_id = current_app.config.get('CURRENT_FORMAT_ID') if format_id is None else format_id
    format = Format.query.get(format_id)
    if format is None:
        logging.error("format ID does not exist in database")
        exit(1)

    last_match = Match.query.filter_by(format_id=format.id).order_by(Match.upload_time.desc()).first()
    if last_match is None:
        logging.error(f"There are no matches for format {format.name} in database; use the scrape-all method instead.")
        exit(2)
    last_match_timestamp = last_match.upload_time
    logging.info(
        f"Timestamp of last match scraped is {last_match_timestamp}. Scraping all matches more recent than this...")

    # query showdown api for all matches in desired format.
    params = {"format": format.name}
    response = requests.get(list_replays_url, params=params)
    if response.status_code != 200:
        logging.error(f"Something went wrong with web request: {response}")
        exit(3)

    matches_json = response.json()
    matches_added_count = 0
    while len(matches_json) > 0:
        for match_json in matches_json:
            if match_json["uploadtime"] >= last_match_timestamp:
                logging.info(f"Processing match {match_json['id']}")
                match_parser = None
                try:
                    match_parser = ShowdownMatchParser.construct_from_json(match_json, format.id, wait, throw_if_exists=True)
                    match_parser.parse_log_details()
                    matches_added_count += 1
                except AlreadyExistsException:
                    logging.info(f"Match {match_json['id']} already exists, skipping.")
                    continue
                except CustomGameException:
                    logging.error("This is a custom game. Will delete any data populated by it and skip.")
                    if match_parser:
                        db.session.delete(match_parser.match_record)
                        db.session.commit()
                    continue
                except Exception as e:
                    # any exception thrown beyond AlreadyExistsException is a genuine processing error. log it and continue
                    logging.error(f"ERROR processing match {match_json['id']}: {e}")
                    error_json = {
                        "showdown_id": match_json['id'],
                        "error": str(e),
                        "match_json": match_json
                    }
                    with open(error_file_name, 'a', encoding='utf-8') as f:
                        f.write(json.dumps(error_json) + "\n")
                    if match_parser:
                        db.session.delete(match_parser.match_record)
                        db.session.commit()
                    continue

            else:
                logging.info(f"Match {match_json['id']} with timestamp {match_json['uploadtime']} is older than"
                             f" {last_match_timestamp}. Match scraping is complete. Added {matches_added_count} matches "
                             f"to database.")
                return

        # 51 is the limit of matches that can be returned by this call, so if there are 51, there might be more results
        # on the next page. Query for those.
        if len(matches_json) == 51:
            params["before"] = matches_json[-1]['uploadtime']
            logging.info(
                f"Processed all results from this page, getting more matches before timestamp {params['before']}")
            response = requests.get(list_replays_url, params=params)
            if response.status_code != 200:
                logging.error(f"Something went wrong with web request: {response}")
                exit(1)
            else:
                matches_json = response.json()
        else:
            logging.info(f"There were {len(matches_json)} matches in these results, so we've seen everything")
            matches_json = []

        # invalidate pokemon stats cache now that new data is present
        keys = redis_cache.keys(f"pokemon_stats:{format_id}:*")
        if keys:
            redis_cache.delete(*keys)
            logging.info(f"Cleared {len(keys)} cached entries for format {format_id}")


@showdown.command('scrape-historic')
@click.option('--format_id', '-f', type=int)
@click.option('--wait', '-w', is_flag=True, default=True,
              help='whether to wait REQUEST_DELAY seconds before calling showdown API (to not hammer it or get rate limited)')
def scrape_historic(format_id, wait):
    logging.basicConfig(level=logging.INFO)
    error_file_name = os.path.join(os.getcwd(), 'app', 'tasks', 'errors', f'scrape-historic-{int(time.time())}.json')

    # get the format id - default to current as specified in config if no value is provided
    format_id = current_app.config.get('CURRENT_FORMAT_ID') if format_id is None else format_id
    format = Format.query.get(format_id)
    if format is None:
        logging.error("format ID does not exist in database")
        exit(1)

    earliest_match = Match.query.filter_by(format_id=format.id).order_by(Match.upload_time.asc()).first()
    if earliest_match is None:
        logging.error(f"There are no matches for format {format.name} in database; use the scrape-all method instead.")
        exit(2)
    logging.info(
        f"Timestamp of earliest match scraped is {earliest_match.upload_time}. Scraping all matches older than this...")

    # query showdown api for all matches in desired format.
    params = {
        "format": format.name,
        "before": earliest_match.upload_time
    }
    response = requests.get(list_replays_url, params=params)
    if response.status_code != 200:
        logging.error(f"Something went wrong with web request: {response}")
        exit(3)

    matches_json = response.json()
    matches_added_count = 0
    while len(matches_json) > 0:
        for match_json in matches_json:
            logging.info(f"Processing match {match_json['id']}")
            match_parser = None
            try:
                match_parser = ShowdownMatchParser.construct_from_json(match_json, format.id, wait, throw_if_exists=True)
                match_parser.parse_log_details()
                matches_added_count += 1
            except AlreadyExistsException:
                # a record for the match already exists; continue to the next one
                logging.info("Match already exists, skipping.")
                continue
            except CustomGameException:
                logging.error("This is a custom game. Will delete any data populated by it and skip.")
                if match_parser:
                    db.session.delete(match_parser.match_record)
                    db.session.commit()
                continue
            except Exception as e:
                # any exception thrown beyond AlreadyExistsException is a genuine processing error. log it and continue
                logging.error(f"ERROR processing match {match_json['id']}: {e}")
                error_json = {
                    "showdown_id": match_json['id'],
                    "error": str(e),
                    "match_json": match_json
                }
                with open(error_file_name, 'a', encoding='utf-8') as f:
                    f.write(json.dumps(error_json) + "\n")
                if match_parser:
                    db.session.delete(match_parser.match_record)
                    db.session.commit()
                continue

        # 51 is the limit of matches that can be returned by this call, so if there are 51, there might be more results
        # on the next page. Query for those.
        if len(matches_json) == 51:
            params["before"] = matches_json[-1]['uploadtime']
            logging.info(
                f"Processed all results from this page, getting more matches before timestamp {params['before']}")
            response = requests.get(list_replays_url, params=params)
            if response.status_code != 200:
                logging.error(f"Something went wrong with web request: {response}")
                exit(1)
            else:
                matches_json = response.json()
        else:
            logging.info(f"There were {len(matches_json)} matches in these results, so we've seen everything")
            matches_json = []

        # invalidate pokemon stats cache now that new data is present
        keys = redis_cache.keys(f"pokemon_stats:{format_id}:*")
        if keys:
            redis_cache.delete(*keys)
            logging.info(f"Cleared {len(keys)} cached entries for format {format_id}")




@showdown.command('scrape-all')
@click.option('--format_id', '-f', type=int)
@click.option('--wait', '-w', is_flag=True, default=False,
              help='whether to wait REQUEST_DELAY seconds before calling showdown API (to not hammer it or get rate limited)')
@click.option('--reprocess_seen', '-rs', is_flag=True, default=False,
              help='whether to reprocess matches that already have records in the database. Set to true when data might '
                   'be missing.')
def scrape_all(format_id, wait, reprocess_seen):
    logging.basicConfig(level=logging.INFO)
    error_file_name = os.path.join(os.getcwd(), 'app', 'tasks', 'errors', f'scrape-all-{int(time.time())}.json')

    # get the format id - default to current as specified in config if no value is provided
    format_id = current_app.config.get('CURRENT_FORMAT_ID') if format_id is None else format_id
    format = Format.query.get(format_id)
    if format is None:
        logging.error("format ID does not exist in database")
        exit(1)

    # query showdown api for all matches in desired format.
    params = {"format": format.name}
    response = requests.get(list_replays_url, params=params)
    if response.status_code != 200:
        logging.error(f"Something went wrong with web request: {response}")
        exit(3)

    matches_json = response.json()
    matches_added_count = 0
    while len(matches_json) > 0:
        for match_json in matches_json:
            logging.info(f"Processing match {match_json['id']}")
            match_parser = None
            try:
                match_parser = ShowdownMatchParser.construct_from_json(match_json, format.id, wait, throw_if_exists=False if reprocess_seen else True)
                match_parser.parse_log_details()
                matches_added_count += 1
            except AlreadyExistsException:
                # a record for the match already exists; continue to the next one
                logging.info("Match already exists, skipping.")
                continue
            except CustomGameException:
                logging.error("This is a custom game. Will delete any data populated by it and skip.")
                if match_parser:
                    db.session.delete(match_parser.match_record)
                    db.session.commit()
                continue
            except Exception as e:
                # any exception thrown beyond AlreadyExistsException is a genuine processing error. log it and continue
                logging.error(f"ERROR processing match {match_json['id']}: {e}")
                error_json = {
                    "showdown_id": match_json['id'],
                    "error": str(e),
                    "match_json": match_json
                }
                with open(error_file_name, 'a', encoding='utf-8') as f:
                    f.write(json.dumps(error_json) + "\n")
                if match_parser:
                    db.session.delete(match_parser.match_record)
                    db.session.commit()
                continue

        # 51 is the limit of matches that can be returned by this call, so if there are 51, there might be more results
        # on the next page. Query for those.
        if len(matches_json) == 51:
            params["before"] = matches_json[-1]['uploadtime']
            logging.info(
                f"Processed all results from this page, getting more matches before timestamp {params['before']}")
            response = requests.get(list_replays_url, params=params)
            if response.status_code != 200:
                logging.error(f"Something went wrong with web request: {response}")
                exit(1)
            else:
                matches_json = response.json()
        else:
            logging.info(f"There were {len(matches_json)} matches in these results, so we've seen everything")
            matches_json = []

        # invalidate pokemon stats cache now that new data is present
        keys = redis_cache.keys(f"pokemon_stats:{format_id}:*")
        if keys:
            redis_cache.delete(*keys)
            logging.info(f"Cleared {len(keys)} cached entries for format {format_id}")


@showdown.command('assign-set')
def assign_set_id():
    logging.basicConfig(level=logging.INFO)

    set_id = db.session.query(Match.set_id).order_by(Match.set_id.desc()).first()
    set_id = set_id[0] + 1 if set_id[0] is not None else 0
    logging.info(f"Will start incrementing set ids from {set_id}")
    batch_size = 100
    offset = 0

    pm1 = aliased(PlayerMatch)
    pm2 = aliased(PlayerMatch)
    p1 = aliased(Player)
    p2 = aliased(Player)
    m1 = aliased(Match)

    while True:
        batch_query = db.session\
            .query(
                pm1.player_id.label("p1_id"),
                p1.name.label('p1_name'),
                pm2.player_id.label("p2_id"),
                p2.name.label('p2_name'),
                literal_column("GROUP_CONCAT(matches.position_in_set, '|', matches.id, '|', matches.showdown_id ORDER BY matches.showdown_id SEPARATOR ',')").label('match_list'),
                Match.format_id.label('format')
            ).join(p1, pm1.player_id == p1.id)\
            .join(pm2, pm1.match_id == pm2.match_id)\
            .join(p2, pm2.player_id == p2.id)\
            .join(Match, pm1.match_id == Match.id)\
            .filter(
                Match.set_id.is_(None),
                Match.position_in_set.is_not(None),
                pm1.player_id < pm2.player_id,
            ).group_by(
                pm1.player_id,
                p1.name,
                pm2.player_id,
                p2.name,
                Match.format_id
            ).limit(batch_size)

        #logging.info(f'Will update set id with statement {batch_query.statement.compile(compile_kwargs={"literal_binds": True})}')
        batch = batch_query.all()

        if not batch:
            logging.info(f"Did not find any matches without set_id to process. exiting.")
            break

        for result in batch:
            logging.info('-------------------')
            logging.info(f"Parsing record {result}")

            all_match_data = []
            for m in result[4].split(','):
                m = m.split("|")
                all_match_data.append({
                    'position': int(m[0]),
                    'id': int(m[1]),
                    'showdown_id': m[2],
                    'pokemon': None
                })

            # get all pokemon used by match:
            pokemon_data_base_query = db.session.query(
                PlayerMatch.match_id,
                literal_column("GROUP_CONCAT(pm_pokemon.pokemon_id ORDER BY pm_pokemon.pokemon_id SEPARATOR ',')").label('poke_list'),
            ).select_from(
                PlayerMatch
            ).join(
                PlayerMatchPokemon, PlayerMatch.id == PlayerMatchPokemon.player_match_id
            ).group_by(
                PlayerMatch.match_id
            )

            pokemon_data = pokemon_data_base_query.filter(
                PlayerMatch.match_id.in_([x['id'] for x in all_match_data])
            ).all()
            poke_match_map = {int(x[0]): x[1] for x in pokemon_data}

            logging.info(f"match to pokemon map {poke_match_map}")

            # loop through all the matches and group them into sets.
            match_sets = []
            match_set = {1: None, 2: None, 3: None}
            previous = 0
            for match in all_match_data:
                # assign the pokemon to the match for comparison
                if match['id'] not in poke_match_map.keys():
                    logging.error(f"Could not locate pokemon for match with id {match['id']}")
                    exit(9)
                match['pokemon'] = poke_match_map[match['id']]

                logging.info(f"Processing match {match}")

                #if the current match position is lower than the previous or is already filled in this set, then we've
                # looped around to a new set. Add the previous set to the list and start populating a new one
                if match['position'] <= previous or match_set[match['position']] is not None:
                    logging.info(f"Match {match['id']} position {match['position']} is less than previous position {previous}; adding new set.")
                    match_sets.append(match_set)
                    match_set = {1: None, 2: None, 3: None}

                # check to make sure the pokemon match any previous matches in the set. If not, it's a new set.
                elif match['position'] > 1 and previous != 0 and match['pokemon'] != match_set[previous]['pokemon']:
                    logging.info(f'match {match['id']} at position {match['position']} has different pokemon than previous\n'
                          f'({match['pokemon']} versus {match_set[previous]['pokemon']})\n'
                          f'creating new set.')
                    match_sets.append(match_set)
                    match_set = {1: None, 2: None, 3: None}

                match_set[match['position']] = match
                previous = match['position']

            match_sets.append(match_set)
            logging.info(f'found {len(match_sets)} match sets')

            # assign a set id to each defined set of matches
            for match_index, match_set in enumerate(match_sets):
                # if the first set of matches is missing it's first match, this might be part of an existing series
                # that was already catalogued in the database earlier. If so, we will search for the match immediately
                # preceding the first present in this set and determine if they're a match by the pokemon used in them.
                # if so, give all items in this match set the same set id as the existing series.
                if match_index == 0 and match_set[1] is None:
                    logging.info(f"\tFirst match in set {match_index} is missing; will query for existing set to append to")
                    earliest_position = 2 if match_set[2] else 3
                    showdown_id = match_set[earliest_position]['showdown_id']

                    prev_set = db.session \
                        .query(
                            Match.id,
                            Match.set_id,
                            Match.position_in_set,
                            Match.upload_time
                        ).join(pm1, pm1.match_id == Match.id)\
                        .join(p1, pm1.player_id == p1.id) \
                        .join(pm2, pm2.match_id == Match.id) \
                        .join(p2, pm2.player_id == p2.id) \
                        .filter(
                            Match.set_id.is_not(None),
                            Match.showdown_id < showdown_id,
                            Match.position_in_set < earliest_position,
                            pm1.player_id < pm2.player_id,
                            pm1.player_id == result[0],
                            pm2.player_id == result[2],
                            ~exists().where(
                                m1.set_id == Match.set_id,
                                m1.position_in_set == earliest_position
                            )
                        ).order_by(Match.showdown_id.desc())\
                        .first()

                    if prev_set is not None:
                        logging.info(f'Found possible previous set with id {prev_set[0]}; checking pokemon to verify')
                        prev_match_pokemon = pokemon_data_base_query.filter(PlayerMatch.match_id == prev_set[0]).first()
                        logging.info(f'prev_match_pokemon: {prev_match_pokemon}')

                        if all([True if x['pokemon'] == prev_match_pokemon[1] else False for x in match_set.values() if x is not None]):
                            logging.info(f"Also matched previous pokemon!")
                            logging.info(f"Appending this match to existing set with set_id {prev_set.set_id}")
                            stmt = update(Match).where(Match.id.in_([x['id'] for x in match_set.values() if x is not None])).values(set_id=prev_set.set_id)
                            db.session.execute(stmt)
                            continue
                    else:
                        logging.info("No existing set found to match this record. Will create new set id for it.")

                set_match_ids = [x['id'] for x in match_set.values() if x is not None]
                logging.info(f"Assigning match ids {set_match_ids} to set id {set_id}")
                stmt = update(Match).where(Match.id.in_(set_match_ids)).values(set_id=set_id)
                #logging.info(f'Will update set id with statement {stmt.compile(compile_kwargs={"literal_binds": True})}')
                db.session.execute(stmt)
                set_id += 1

            db.session.commit()

        db.session.commit()
        db.session.expunge_all()
        offset += batch_size
        logging.info('fetching next batch of match records.')

    logging.info(f"Finished assigning set_ids")
