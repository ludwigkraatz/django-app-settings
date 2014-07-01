from app_settings import AppSettings


def validate_settings(attr, val):
    pass


config = {
    'NAME': 'MY_APP',

    'SETTINGS': {
        'DEBUG': None,  # if None, it returns the global DEBUG value
        'SETTINGS_1': None,
    },

    'DEFAULTS': {
        'SETTINGS_1': 1,
    },

    # List of settings that may be in string import notation.
    'IMPORT_STRINGS': (
    ),

    'VALIDATION_METHOD': validate_settings
}


settings = AppSettings(config)
