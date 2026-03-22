import keyring

# local environment configuration
class LocalConfig(object):
    # MySQL configuration
    MYSQL_USER = keyring.get_password("replaygenie","mysql_username")
    MYSQL_PASSWORD = keyring.get_password("replaygenie","mysql_password")
    MYSQL_HOST = "localhost"
    MYSQL_DB = "replaygenie"
    SQLALCHEMY_DATABASE_URI = f'mysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}/{MYSQL_DB}'

    BASE_URL = 'http://localhost:5000'


