import json
import logging
import os
import time
import click
import requests
from flask import current_app
from sqlalchemy import literal_column, update, exists
from sqlalchemy.orm import aliased
from app import db
from app.exceptions import AlreadyExistsException
from app.models import Format, Match, PlayerMatch, Player
from app.tasks import bp
from app.tasks.showdown_match_parser import ShowdownMatchParser

list_replays_url = "https://replay.pokemonshowdown.com/search.json"


@bp.cli.group()
def showdown():
    """Commands to scrape matches from showdown urls"""
    pass

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
                try:
                    match_parser = ShowdownMatchParser.construct_from_json(match_json, format.id, wait, throw_if_exists=True)
                    match_parser.parse_log_details()
                    matches_added_count += 1
                except AlreadyExistsException:
                    logging.info(f"Match {match_json['id']} already exists, skipping.")
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
            try:
                match_parser = ShowdownMatchParser.construct_from_json(match_json, format.id, wait, throw_if_exists=True)
                match_parser.parse_log_details()
                matches_added_count += 1
            except AlreadyExistsException:
                # a record for the match already exists; continue to the next one
                logging.info("Match already exists, skipping.")
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
            try:
                match_parser = ShowdownMatchParser.construct_from_json(match_json, format.id, wait, throw_if_exists=False if reprocess_seen else True)
                match_parser.parse_log_details()
                matches_added_count += 1
            except AlreadyExistsException:
                # a record for the match already exists; continue to the next one
                logging.info("Match already exists, skipping.")
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


@showdown.command('assign-set')
@click.option('--query_missing', '-q', is_flag=True, default=False,
              help='searches the showdown api for any matches missing in the sequence')
def assign_set_id(query_missing):
    logging.basicConfig(level=logging.INFO)
    format_cache = {}

    set_id = db.session.query(Match.set_id).order_by(Match.set_id.desc()).first()
    set_id = set_id[0] + 1 if set_id[0] is not None else 0
    logging.info(f"Will start incrementing set ids from {set_id}")
    batch_size = 10
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
                literal_column("GROUP_CONCAT(matches.position_in_set, '|', matches.id, '|', matches.showdown_id ORDER BY matches.upload_time SEPARATOR ',')").label('match_list'),
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
            matches = [x.split('|') for x in result[4].split(",")]
            if query_missing:
                logging.info(f"Will query showdown to fetch any missing matches")
                if result[5] not in format_cache:
                    format_record = Format.query.get(result[5])
                    format_cache[result[5]] = format_record.name

                search_url = "https://replay.pokemonshowdown.com/search.json"
                params = {
                    "user": result[1],
                    "user2": result[3],
                    "format": format_cache[result[5]]
                }
                response = requests.get(search_url, params=params)
                if response.status_code != 200:
                    logging.error(f"Something went wrong with web request: {response}")
                if len(response.json()) < len(matches):
                    logging.error(f"Somehow we have less in the response than in the db? Double check this")
                    exit(30)
                else:
                    new_match_json = {x['id'].split('-')[1]: x for x in response.json()}
                    for showdown_id, match_json in new_match_json.items():
                        if not showdown_id in result[4]:
                            try:
                                match_parser = ShowdownMatchParser.construct_from_json(match_json, result[5], wait=True, throw_if_exists=True)
                                match_parser.parse_log_details()
                                logging.info(f"Created new match record for showdown {showdown_id}")
                                matches.append([
                                    match_parser.match_record.position_in_set,
                                    match_parser.match_record.id,
                                    match_parser.match_record.showdown_id])
                            except AlreadyExistsException:
                                pass

                db.session.commit()
                matches = sorted(matches, key=lambda x: int(x[2]))

            # loop through all the matches and group them into sets.
            match_sets = []
            match_set = {1: None, 2: None, 3: None}
            previous = 0
            for match in matches:
                try:
                    position = int(match[0])
                except ValueError:
                    logging.error(f"match id {match[1]} has null position number.")
                    exit(40)

                if position <= previous or match_set[position] is not None:
                    match_sets.append(match_set)
                    match_set = {1: None, 2: None, 3: None}

                match_set[position] = [match[1], match[2]]
                previous = position
            match_sets.append(match_set)

            logging.info(f'Parsed match sets:: {match_sets}')

            # assign a set id to each defined set of matches
            for match_set in match_sets:
                if match_set[1] is None:
                    # This might be missing data, or it might be a new match to be added to an existing set. query
                    # to see if a set missing a match in this position exists in the database already
                    logging.info(f"First match in set {match_set} is missing; will query for existing set to append to")
                    earliest_position = 2 if match_set[2] else 3
                    showdown_id = match_set[earliest_position][1]

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
                        logging.info(f"Appending this match to existing set with set_id {prev_set.set_id}")
                        stmt = update(Match).where(Match.id.in_([x[0] for x in match_set.values() if x is not None])).values(set_id=prev_set.set_id)
                        db.session.execute(stmt)
                        continue
                    else:
                        logging.info("No existing set found to match this record. Will create new set id for it.")

                stmt = update(Match).where(Match.id.in_([x[0] for x in match_set.values() if x is not None])).values(set_id=set_id)
                #logging.info(f'Will update set id with statement {stmt.compile(compile_kwargs={"literal_binds": True})}')
                db.session.execute(stmt)
                set_id += 1

            db.session.commit()

        db.session.commit()
        db.session.expunge_all()
        offset += batch_size
        logging.info('fetching next batch of match records.')

    logging.info(f"Finished assigning set_ids")