import json
import logging
import os
import time
import click
import requests
from flask import current_app
from app.exceptions import AlreadyExistsException
from app.models import Format, Match
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
                    match_parser = ShowdownMatchParser.construct_from_json(match_json, format, wait, throw_if_exists=True)
                    match_parser.parse_log_details()
                    matches_added_count += 1
                except AlreadyExistsException:
                    # a record for the match already exists; continue to the next one
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
                match_parser = ShowdownMatchParser.construct_from_json(match_json, format, wait, throw_if_exists=True)
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
                match_parser = ShowdownMatchParser.construct_from_json(match_json, format, wait, throw_if_exists=False if reprocess_seen else True)
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
