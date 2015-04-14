from copy import deepcopy
from functools import wraps


def dict_merge(a, b):
    '''recursively merges dict's. not just simple a['key'] = b['key'], if
    both a and bhave a key who's value is a dict then dict_merge is called
    on both values and the result stored in the returned dictionary.'''
    if not isinstance(b, dict):
        return b
    result = deepcopy(a)
    for k, v in b.iteritems():
        if k in result and isinstance(result[k], dict):
                result[k] = dict_merge(result[k], v)
        else:
            result[k] = deepcopy(v)
    return result


class override_app_settings(object):
    """
    Acts as either a decorator, or a context manager. If it's a decorator it
    takes a function and returns a wrapped function. If it's a contextmanager
    it's used with the ``with`` statement. In either event entering/exiting
    are called before and after, respectively, the function/block is executed.
    """
    def __init__(self, settings, options):
        self.options = options
        self.settings = settings

    def __enter__(self):
        self.enable()

    def __exit__(self, exc_type, exc_value, traceback):
        self.disable()

    def __call__(self, test_func):
        from django.test import SimpleTestCase
        if isinstance(test_func, type):
            if not issubclass(test_func, SimpleTestCase):
                raise Exception(
                    "Only subclasses of Django SimpleTestCase can be decorated "
                    "with override_settings")
            self.save_options(test_func)
            return test_func
        else:
            @wraps(test_func)
            def inner(*args, **kwargs):
                with self:
                    return test_func(*args, **kwargs)
        return inner

    def save_options(self, test_func):
        if test_func._overridden_settings is None:
            test_func._overridden_settings = self.options
        else:
            # Duplicate dict to prevent subclasses from altering their parent.
            test_func._overridden_settings = dict(
                test_func._overridden_settings, **self.options)

    def enable(self):
        override = self.settings.with_configuration(self.options)
        self.wrapped = self.settings._wrapped
        self.settings._wrapped = override
        #for key, new_value in self.options.items():
        #    setting_changed.send(sender=self.settings._wrapped.__class__,
        #                         setting=key, value=new_value, enter=True)

    def disable(self):
        self.settings._wrapped = self.wrapped
        del self.wrapped
        #for key in self.options:
        #    new_value = getattr(self.settings, key, None)
        #    setting_changed.send(sender=self.settings._wrapped.__class__,
        #                         setting=key, value=new_value, enter=False)
