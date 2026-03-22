import os

class Config(object):
    STATIC_IMAGES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'app', 'static', 'images')
    POKEMON_IMAGES_DIR = os.path.join(STATIC_IMAGES_DIR, 'pokemon')
    ITEM_IMAGES_DIR = os.path.join(STATIC_IMAGES_DIR, 'items')
    TYPE_IMAGES_DIR = os.path.join(STATIC_IMAGES_DIR, 'types')
    TERA_TYPE_IMAGES_DIR = os.path.join(STATIC_IMAGES_DIR, 'tera')

    # default delay to wait between requests when scraping data so as to not hammer APIs or get rate-limited
    REQUEST_DELAY = 3

    # Config values for use in the UI
    CURRENT_FORMAT_ID = 2
    MIN_ANDROID_VERSION = 1
    MIN_IOS_VERSION = 1
    MIN_WEB_VERSION = 1
    MIN_CATALOG_VERSION = 1

    BASE_URL = 'https://arcvgc.com'