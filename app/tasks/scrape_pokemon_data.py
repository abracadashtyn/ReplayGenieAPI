import enum
import json
import logging
import os
import re
import time

import click
import requests
import unicodedata
from bs4 import BeautifulSoup
from flask import current_app

from app import db
from app.tasks import bp
from app.models import Pokemon, PokemonType, Ability, Item
from app.utils import format_name_to_image_file, remove_accent_marks


@bp.cli.group()
def pokemon():
    """Commands to scrape pokemon information from various sources"""
    pass

@pokemon.command('setup')
@click.pass_context
def setup(ctx):
    ''' Performs all of the commands below in the proper order to populate all necessary pokemon data '''
    click.echo("Populating pokemon types...")
    ctx.invoke(populate_types)
    click.echo("Done.\nPopulating all items and item images from pokemondb...")
    ctx.invoke(scrape_items)
    click.echo("Done.\n Populating pokemon data from serebii...")
    ctx.invoke(scrape_serebii)
    click.echo("Done.\n Populating pokemon data from showdown...")
    ctx.invoke(scrape_showdown)
    click.echo("Done.\n Populating images...")
    ctx.invoke(scrape_images)
    click.echo("Done.")

@pokemon.command('populate-types')
def populate_types():
    types = ['Bug', 'Dark', 'Dragon', 'Electric', 'Fairy', 'Fighting', 'Fire', 'Flying', 'Ghost', 'Grass', 'Ground',
             'Ice', 'Normal', 'Poison', 'Psychic', 'Rock', 'Steel', 'Stellar', 'Water']
    for type in types:
        if PokemonType.query.filter(PokemonType.name == type).first() is None:
            db.session.add(PokemonType(name=type))
    db.session.commit()

@pokemon.command('scrape-items')
def scrape_items():
    allowed_categories = ['Berries', 'Hold items']

    url_to_scrape = "https://pokemondb.net/item/all"
    response = requests.get(url_to_scrape)
    if response.status_code != 200:
        raise Exception(f"Error scraping {url_to_scrape}: {response}")

    page_soup = BeautifulSoup(response.text, "html.parser")

    item_table = page_soup.find('table', attrs={'class': 'data-table'})
    if item_table is None:
        raise Exception(f"Error scraping {url_to_scrape}: could not find data table in response. ")

    for row in item_table.find('tbody').find_all('tr'):
        cells = row.find_all('td')
        name, type = cells[0], cells[1]
        name = cells[0].text.strip()
        type = type.text.strip()

        if type in allowed_categories:
            click.echo(f"Processing item {name}")
            item_record = Item.get_or_create(name)
            item_image_url = cells[0].find('img').get('src')

            # check to make sure this isn't the 1x1 placeholder png image. If it is, skip and try to fetch from a
            # different source later
            if os.path.basename(item_image_url) == 's.png':
                click.echo(f"Skipping fetch image for {name} as this source does not have it. ")
                continue

            item_image_file = os.path.join(current_app.config['ITEM_IMAGES_DIR'], format_name_to_image_file(item_record.name))
            if not os.path.exists(item_image_file):
                click.echo(f"Waiting {current_app.config['REQUEST_DELAY']} seconds then fetching item image from {item_image_url}")
                time.sleep(current_app.config['REQUEST_DELAY'])
                item_image_response = requests.get(item_image_url, timeout=10)

                # if there is a problem fetching the image just continue; can fetch from other sources in other methods
                if item_image_response.status_code != 200:
                    click.echo(f"ERROR: fetching: {item_image_response}")
                    continue
                with open(item_image_file, 'wb') as f:
                    f.write(item_image_response.content)


@pokemon.command('scrape-serebii')
@click.option('--localmode', '-l', 'local_mode', is_flag=True, default=False,
              help='if true, pulls from serebii data in static test data files, and fails if file does not exist.')
@click.option('--savedata', '-s', 'save_data', is_flag=True, default=False,
              help='Preserves data pulled from serebii in static files')
def scrape_serebii(local_mode, save_data):
    file_path = os.path.join(os.getcwd(), 'app', 'static', 'test_data', 'serebii_pokedex.html')
    if local_mode:
        # open saved file from above, for testing purposes
        with open(file_path, 'r', encoding='utf-8') as f:
            page_soup = BeautifulSoup(f.read(), "html.parser")
    else:
        url_to_scrape = "https://www.serebii.net/pokemon/nationalpokedex.shtml"
        response = requests.get(url_to_scrape)
        if response.status_code != 200:
            logging.error(f"Error scraping {url_to_scrape}: {response}")
            raise Exception("Failed to scrape serebii.")
        page_soup = BeautifulSoup(response.text, "html.parser")

        if save_data:
            with open(file_path, 'w+', encoding='utf-8') as f:
                f.write(page_soup.prettify())


    dex_table = page_soup.find('table', attrs={'class': 'dextable'})
    if dex_table is None:
        raise Exception("Failed to scrape serebii: Could not find dextable in page.")

    rows = dex_table.find_all('tr')
    for row in rows:
        tds = row.find_all('td', attrs={'class': 'fooinfo'})
        if tds is not None and len(tds) > 0:
            pkmn_id = tds[0].get_text(strip=True)
            pkmn_id = int(pkmn_id.lstrip("#"))
            pkmn_name = tds[2].get_text(strip=True)

            # skip if this name has any special characters in it i.e. Nidoran male or female, which showdown has in
            # a better format
            if any([True if unicodedata.category(x).startswith('S') else False for x in pkmn_name]):
                click.echo(f"Skipping {pkmn_name}")
                continue

            pkmn_record = Pokemon.get_or_create(pkmn_name, pkmn_id)
            for type in tds[3].find_all('a'):
                type_name = type.get('href').split('/')[-1]
                type_record = PokemonType.get_or_create(type_name.capitalize())
                if type_record not in pkmn_record.types:
                    pkmn_record.types.append(type_record)
            click.echo(f"Added record for #{pkmn_id} {pkmn_name}")
            db.session.commit()


@pokemon.command('scrape-showdown')
@click.option('--localmode', '-l', 'local_mode', is_flag=True, default=False,
              help='if true, pulls from showdown data in static test data files, and fails if file does not exist.')
@click.option('--savedata', '-s', 'save_data', is_flag=True, default=False,
              help='Preserves data pulled from showdown in static files')
def scrape_showdown(local_mode, save_data):
    file_path = os.path.join(os.getcwd(), 'app', 'static', 'test_data', 'showdown_pokedex.json')
    if local_mode:
        with open(file_path, 'r', encoding='utf-8') as f:
            poke_data = json.loads(f.read())
    else:
        query_url = 'https://play.pokemonshowdown.com/data/pokedex.json'
        response = requests.get(query_url)
        if response.status_code != 200:
            logging.error(f"Error scraping {query_url}: {response}")
            raise Exception("Failed to scrape showdown.")
        poke_data = response.json()
        if save_data:
            with open(file_path, 'w+', encoding='utf-8') as f:
                f.write(json.dumps(poke_data, indent=4))


    for pokemon in poke_data.values():
        # cosmetic form pokemon have a limited amount of data in them, and don't include even the dex number.
        # have to get all of that from the base species
        if 'isCosmeticForme' in pokemon and pokemon['isCosmeticForme'] is True:
            click.echo(f"Parsing cosmetic form pokemon {pokemon['name']}")
            if 'baseSpecies' not in pokemon:
                raise Exception(f"base species for cosmetic form '{pokemon['name']}' not provided.")

            # if the base species does not exist, we can't create it either, as it will have no pokedex number
            parent_record = Pokemon.query.filter(Pokemon.name == pokemon['baseSpecies']).one_or_none()
            if parent_record is None:
                raise Exception(f"Could not find existing record for cosmetic form '{pokemon['name']}'s' baseSpecies {pokemon['baseSpecies']}")

            poke_record = Pokemon.get_or_create(pokemon['name'], parent_record.pokedex_number)
            poke_record.base_species = parent_record
            poke_record.is_cosmetic_only = True
            poke_record.types = parent_record.types
            poke_record.tier = parent_record.tier
            poke_record.is_nonstandard = parent_record.is_nonstandard

            db.session.commit()
            continue

        # remove player-created pokemon that don't have real dex numbers
        if pokemon['num'] < 0:
            continue

        click.echo(f"Parsing pokemon #{pokemon['num']} {pokemon['name']}")
        poke_record = Pokemon.get_or_create(pokemon['name'], pokemon['num'])

        if 'tier' in pokemon:
            poke_record.tier = pokemon['tier']
        if 'isNonstandard' in pokemon:
            poke_record.is_nonstandard = pokemon['isNonstandard']

        # if this pokemon is a subform of another pokemon, set the base_form column
        if 'baseSpecies' in pokemon and pokemon['baseSpecies'] != pokemon['name']:
            poke_record.base_species = Pokemon.get_or_create(pokemon['baseSpecies'], pokemon['num'])


        # associate any types, adding records if needed
        if 'types' in pokemon:
            for type in pokemon['types']:
                poke_type = PokemonType.get_or_create(type)
                if poke_type not in poke_record.types:
                    poke_record.types.append(poke_type)

        # add any abilities found on the entry, but don't associate with pokemon until match time
        if 'abilities' in pokemon:
            for x, ability in pokemon['abilities'].items():
                Ability.get_or_create(ability)

        db.session.commit()

""" Wrapper command to scrape all images using functions below"""
@pokemon.command('scrape-images')
@click.pass_context
def scrape_images(ctx):
    ctx.invoke(scrape_pokemon_images_cmd)
    ctx.invoke(scrape_type_images_cmd)
    ctx.invoke(scrape_item_images_cmd)
    ctx.invoke(scrape_tera_type_images_cmd)


""" Scrape pokemon images"""
def scrape_pokemon_image(pokemon_record):
    pokemon_image_base_url = "https://play.pokemonshowdown.com/sprites/home-centered/"

    showdown_formatted_name = ''.join([x.lower() for x in pokemon_record.name if x.isalnum()])
    if pokemon_record.base_species is not None:
        base_species_formatted_name = ''.join([x.lower() for x in pokemon_record.base_species.name if x.isalnum()])
        name_regex = re.search(f'({base_species_formatted_name})(.*)', showdown_formatted_name)
        if name_regex is not None:
            showdown_formatted_name = f'{name_regex.group(1)}-{name_regex.group(2)}'
        else:
            raise Exception(
                f"Could not find base species name {base_species_formatted_name} in {showdown_formatted_name}")

    # check if the image already exists, and fetch if not
    pokemon_image_file = os.path.join(current_app.config['POKEMON_IMAGES_DIR'], format_name_to_image_file(pokemon_record.name))
    if not os.path.exists(pokemon_image_file):
        pokemon_image_url = f'{pokemon_image_base_url}{remove_accent_marks(showdown_formatted_name)}.png'
        click.echo(f"Waiting {current_app.config['REQUEST_DELAY']} seconds then fetching pokemon image from {pokemon_image_url}")
        time.sleep(current_app.config['REQUEST_DELAY'])
        pokemon_image_response = requests.get(pokemon_image_url, timeout=10)

        if pokemon_image_response.status_code != 200:
            click.echo(f"ERROR: could not fetch pokemon image. CODE {pokemon_image_response.status_code}: "
                       f"{pokemon_image_response.reason}")
            return

        with open(pokemon_image_file, 'wb') as f:
            f.write(pokemon_image_response.content)

@pokemon.command('scrape-pokemon-images')
def scrape_pokemon_images_cmd():
    pokemon = Pokemon.query.order_by(Pokemon.id).all()
    for record in pokemon:
        click.echo(f"Scraping image for pokemon {record.pokemon_name}")
        scrape_pokemon_image(record)

@pokemon.command('scrape-pokemon-image')
@click.option('--id', '-i', 'pokemon_id',type=click.INT, help='the id of the pokemon to fetch the image for')
@click.option('--name', '-n', 'pokemon_name',type=click.STRING, help='the name of the pokemon to fetch the image for')
def scrape_pokemon_image_cmd(pokemon_id, pokemon_name):
    if pokemon_id is not None:
        record = db.session.get(Pokemon, pokemon_id)
    elif pokemon_name is not None:
        record = Pokemon.query.filter(Pokemon.name == pokemon_name).one_or_none()
    else:
        click.echo("Must provide either id or name - to fetch images for all pokemon use 'scrape-pokemon-images' instead.")
        return

    if record is not None:
        click.echo(f"Scraping image for pokemon {record.pokemon_name}")
        scrape_pokemon_image(record)
    else:
        click.echo("Could not find the pokemon specified by id or name.")


""" Item Image Functions"""
def scrape_item_image(item_name):
    item_image_base_url = 'https://www.serebii.net/itemdex/sprites/sv/'
    serebii_formatted_name = ''.join([x.lower() for x in item_name if x.isalnum()])
    item_image_file = os.path.join(current_app.config['ITEM_IMAGES_DIR'], format_name_to_image_file(item_name))
    if not os.path.exists(item_image_file):
        item_image_url = f'{item_image_base_url}{serebii_formatted_name}.png'
        click.echo(f"Waiting {current_app.config['REQUEST_DELAY']} seconds then fetching item image from {item_image_url}")
        time.sleep(current_app.config['REQUEST_DELAY'])
        item_image_response = requests.get(item_image_url, timeout=10)
        if item_image_response.status_code != 200:
            click.echo(f"ERROR: could not fetch pokemon image. CODE {item_image_response.status_code}: "
                       f"{item_image_response.reason}")
            return
        with open(item_image_file, 'wb') as f:
            f.write(item_image_response.content)

@pokemon.command('scrape-item-images')
def scrape_item_images_cmd():
    items = Item.query.all()
    for item in items:
        scrape_item_image(item.name)

@pokemon.command('scrape-item-image')
@click.option('--id', '-i', 'item_id',type=click.INT, help='the id of the item to fetch the image for')
@click.option('--name', '-n', 'item_name',type=click.STRING, help='the name of the item to fetch the image for')
def scrape_item_image_cmd(item_id, item_name):
    if item_id is not None:
        record = db.session.get(Item, item_id)
    elif item_name is not None:
        record = Item.query.filter(Item.name == item_name).one_or_none()
    else:
        click.echo("must provide either id or name - to fetch images for all items use 'scrape-item-images' instead.")
        return

    if record is not None:
        click.echo(f"Scraping image for item {record.name}")
        scrape_item_image(record.name)
    else:
        click.echo("Could not find the item specified by id or name.")


""" Type Image Functions"""
def scrape_type_image(type_name):
    type_image_base_url = 'https://www.serebii.net/pokedex-sv/type/icon/'
    serebii_formatted_name = ''.join([x.lower() for x in type_name if x.isalnum()])
    type_image_file = os.path.join(current_app.config['TYPE_IMAGES_DIR'], format_name_to_image_file(type_name))
    if not os.path.exists(type_image_file):
        type_image_url = f'{type_image_base_url}{serebii_formatted_name}.png'
        click.echo(f"Waiting {current_app.config['REQUEST_DELAY']} seconds then fetching type image from {type_image_url}")
        time.sleep(current_app.config['REQUEST_DELAY'])
        type_image_response = requests.get(type_image_url, timeout=10)
        if type_image_response.status_code != 200:
            click.echo(f"ERROR: could not fetch pokemon image. CODE {type_image_response.status_code}: "
                       f"{type_image_response.reason}")
            return
        with open(type_image_file, 'wb') as f:
            f.write(type_image_response.content)

# TODO add command for individual type image

@pokemon.command('scrape-type-images')
def scrape_type_images_cmd():
    types = PokemonType.query.all()
    for type in types:
        scrape_type_image(type.name)


""" Tera type image functions """
def scrape_tera_type_image(tera_type_name):
    tera_type_url = 'https://play.pokemonshowdown.com/sprites/types/'
    type_image_file = os.path.join(current_app.config['TERA_TYPE_IMAGES_DIR'], format_name_to_image_file(tera_type_name))
    if not os.path.exists(type_image_file):
        type_image_url = f'{tera_type_url}Tera{tera_type_name}.png'
        click.echo(
            f"Waiting {current_app.config['REQUEST_DELAY']} seconds then fetching type image from {type_image_url}")
        time.sleep(current_app.config['REQUEST_DELAY'])
        type_image_response = requests.get(type_image_url, timeout=10)
        if type_image_response.status_code != 200:
            click.echo(f"ERROR: could not fetch tera type image. CODE {type_image_response.status_code}: "
                       f"{type_image_response.reason}")
            return
        with open(type_image_file, 'wb') as f:
            f.write(type_image_response.content)

# TODO add command for individual tera type image

@pokemon.command('scrape-tera-types')
def scrape_tera_type_images_cmd():
    types = PokemonType.query.all()
    for type in types:
        scrape_tera_type_image(type.name)



@pokemon.command('validate-images')
@click.option('--type', '-t',
              type=click.Choice(['pokemon', 'item', 'type', 'teratype', 'all'], case_sensitive=False),
              default='all',
              help='the type of image being added. Will affect which table is being referenced.')
def validate_images(type):
    if type == 'pokemon' or type == 'all':
        all_pokemon = Pokemon.query.all()
        for pokemon in all_pokemon:
            pokemon_image_file = os.path.join(current_app.config['POKEMON_IMAGES_DIR'], format_name_to_image_file(pokemon.name))
            if not os.path.exists(pokemon_image_file):
                click.echo(f"Could not find image for pokemon {pokemon.name} (id {pokemon.id})")

    if type == 'item' or type == 'all':
        all_items = Item.query.all()
        for item in all_items:
            item_image_file = os.path.join(current_app.config['ITEM_IMAGES_DIR'], format_name_to_image_file(item.name))
            if not os.path.exists(item_image_file):
                click.echo(f"Could not find image for item {item.name} (id {item.id})")

    if type == 'type' or type == 'all':
        all_types = PokemonType.query.all()
        for type in all_types:
            type_image_file = os.path.join(current_app.config['TYPE_IMAGES_DIR'], format_name_to_image_file(type.name))
            if not os.path.exists(type_image_file):
                click.echo(f"Could not find image for type {type.name} (id {type.id})")

    if type == 'teratype' or type == 'all':
        all_teratypes = PokemonType.query.all()
        for teratype in all_teratypes:
            teratype_image_file = os.path.join(current_app.config['TERA_TYPE_IMAGES_DIR'], teratype.name)
            if not os.path.exists(teratype_image_file):
                click.echo(f"Could not find image for type {teratype.name} (id {teratype.id})")


@pokemon.command('manual-add-image')
@click.option('--type', '-t',
              type=click.Choice(['pokemon', 'item', 'type', 'teratype'], case_sensitive=False),
              default='pokemon',
              help='the type of image being added. Will affect which table is being referenced.')
@click.option('--id', '-i', type=click.INT,
              help='The ID of the record in the appropriate table to add an image for.')
@click.option('--url', '-u', type=click.STRING, help='The URL of the image to add.')
def manual_add_image(type, id, url):
    record = None
    image_file = None
    if type == 'pokemon':
        record = Pokemon.query.get(id)
        image_file = os.path.join(current_app.config['POKEMON_IMAGES_DIR'], format_name_to_image_file(record.name))
    elif type == 'item':
        record = Item.query.get(id)
        image_file = os.path.join(current_app.config['ITEM_IMAGES_DIR'], format_name_to_image_file(record.name))
    elif type == 'type':
        record = PokemonType.query.get(id)
        image_file = os.path.join(current_app.config['TYPE_IMAGES_DIR'], format_name_to_image_file(record.name))
    elif type == 'teratype':
        record = PokemonType.query.get(id)
        image_file = os.path.join(current_app.config['TERA_TYPE_IMAGES_DIR'],format_name_to_image_file(record.name))

    else:
        click.echo(f"Error: Unknown type {type}")
        exit(1)

    if record is None:
        click.echo(f"Error: No record found for {type} id {id}")
        exit(2)

    click.echo(f"Fetching image for {record.name} from url {url}")
    image = requests.get(url, timeout=10)
    if image.status_code != 200:
        click.echo(f"ERROR: could not fetch {record.name} image. CODE {image.status_code}")

    with open(image_file, 'wb') as f:
        f.write(image.content)





