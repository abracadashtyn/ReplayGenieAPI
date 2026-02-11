import os

class Config(object):
    STATIC_IMAGES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'app', 'static', 'images')
    POKEMON_IMAGES_DIR = os.path.join(STATIC_IMAGES_DIR, 'pokemon')
    ITEM_IMAGES_DIR = os.path.join(STATIC_IMAGES_DIR, 'items')
    TYPE_IMAGES_DIR = os.path.join(STATIC_IMAGES_DIR, 'types')

    # default delay to wait between requests when scraping data so as to not hammer APIs or get rate-limited
    REQUEST_DELAY = 3