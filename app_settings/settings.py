import logging
from django.conf import settings
from django.utils.functional import LazyObject, empty
from django.utils import importlib


def perform_import(settings_name, val, setting_lookup):
    """
    If the given setting is a string import notation,
    then perform the necessary import or imports.
    """
    if isinstance(val, basestring):
        return import_from_string(settings_name, val, setting_lookup)
    elif isinstance(val, (list, tuple)):
        return [import_from_string(settings_name, item, setting_lookup) for item in val]
    return val


def perform_init(settings_name, val, setting_lookup, init_method_location):
    init_method = import_from_string(settings_name, init_method_location, setting_lookup, 'init')
    if not callable(init_method):
        raise Exception('init method "%s" is not callable' % init_method_location)  # TODO: better class

    if isinstance(val, (tuple, list)):
        for value in val:
            if not isinstance(value, SettingsWrapper):
                return val
    elif not isinstance(val, SettingsWrapper):
        return val

    return init_method(val)


def import_from_string(settings_name, val, setting_lookup, scope=None):
    """
    Attempt to import a class from a string representation.
    """
    # TODO: use scope for more detailed Exception message
    parts = val.split('.')
    module_path, class_name = '.'.join(parts[:-1]), parts[-1]
    try:
        # Nod to tastypie's use of importlib.
        module = importlib.import_module(module_path)
        return getattr(module, class_name)
    except Exception:
        raise
        msg = "Could not import Class '%s' from module '%s' for '%s' setting '%s'" % (
            class_name, module_path, settings_name, setting_lookup
        )
        raise ImportError(msg)
    except:
        raise
        msg = "Could not import '%s' for '%s' setting '%s'" % (val, settings_name, setting_lookup)
        raise ImportError(msg)


class SettingsWrapper(object):
    def __init__(self, config, settings, available_settings=None, import_strings=None, validation_method=None,
                 one_to_many=None, parent_settings=None, defaults=None, configuration=None, lookup_path=None,
                 links=None, init=None, upper_settings=None, **kwargs):
        # **kwargs are important for compatibility and can be ignored

        self.__dict__['_config'] = config or {}

        self.__dict__['_dict'] = settings or {}

        self.__dict__['_kwargs'] = {}
        self.__dict__['_kwargs']['lookup_path'] = lookup_path or ''
        self.__dict__['_kwargs']['available_settings'] = available_settings or {}
        self.__dict__['_kwargs']['validation_method'] = validation_method or None

        self.__dict__['_kwargs']['import_strings'] = list(import_strings or [])
        self.__dict__['_kwargs']['one_to_many'] = one_to_many or {}
        self.__dict__['_many_for_one'] = {}
        for key, value in self.__dict__['_kwargs']['one_to_many'].items():
            self.__dict__['_many_for_one'][value] = key

        self.__dict__['_kwargs']['parent_settings'] = parent_settings or None  # is accessed with getattr()
        self.__dict__['_kwargs']['defaults'] = defaults or {}
        self.__dict__['_kwargs']['upper_settings'] = upper_settings or self

        self.__dict__['_kwargs']['links'] = links or {}
        self.__dict__['_kwargs']['init'] = init or {}

        if isinstance(configuration, SettingsWrapper):
            configuration = configuration.as_dict()
        self.__dict__['_kwargs']['configuration'] = configuration or {}

    def as_dict(self):
        return self.__dict__['_dict']

    def deprecation_warning(self, attribute_name):
        pass  # TODO: implement deprecation warning for settings wrapper

    def get_active_configuration(self):
        return self.get_kwarg('configuration')

    def get_configuration_value(self, attribute_name):
        value = None
        configuration = self.get_active_configuration()
        if configuration is not None:
            value = configuration.get(attribute_name, None)
        return value

    def get_value(self, attribute_name):
        value = self.get_configuration_value(attribute_name)

        if value is None:
            value = self.__dict__['_dict'].get(attribute_name, None)

        if value is None and self.get_kwarg('parent_settings') is not None:
            value = getattr(self.get_kwarg('parent_settings'), attribute_name, None)

        if value is None and attribute_name in self.get_kwarg('defaults'):
            value = self.get_kwarg('defaults')[attribute_name]

        return value

    def __getattr__(self, name):
        if name == '_parent':
            return self.get_kwarg('upper_settings')
        return self.get_attribute(name)

    def get_attribute(self, name, filter=None, filter_value=None):
        # TODO: getattr('NESTED.SETTING')
        many_for_one_lookup = self.__dict__['_many_for_one'].get(name, None)
        if name not in self.get_kwarg('available_settings'):
            self.raise_attribute_error(
                attribute_name=name
            )  # TODO: maybe raise SettingNotAvailable or similar
        if ('_DEPRECATED_' + name) in self.get_kwarg('available_settings'):
            self.deprecation_warning(name)

        value = self.get_value(name)
        if value is None and many_for_one_lookup:
            value = self.__getattr__(many_for_one_lookup)
        if value is None:
            self.raise_attribute_error(
                attribute_name=name
            )

        valid = None
        if ('_VALIDATE_' + name) in self.get_kwarg('available_settings'):
            valid = self.get_kwarg('available_settings')['_VALIDATE_' + name](name, value)
        if valid is None and self.get_kwarg('validation_method') is not None:
            valid = self.get_kwarg('validation_method')(name, value)

        if valid is False:
            self.raise_attribute_error(
                attribute_name=name
            )  # TODO: maybe raise SettingsInvalid or similar

        value = self.finalize_value(name, value, filter, filter_value)

        setattr(self, name, value)
        return value

    def get_filtered(self, attribute_name, filter, filter_value):
        return self.get_attribute(attribute_name, filter, filter_value)

    def finalize_value(self, attribute_name, value, filter, filter_value):
        target = None
        if attribute_name in self.get_kwarg('links'):
            link = self.get_kwarg('links')[attribute_name]
            target, filter = link.split('|')

            new_config = self.__dict__['_config']
            link_target = app_settings(new_config).get_filtered(target, filter, value)
            if link_target is None:
                link_target = self.get_filtered(target, filter, value)
                if link_target is None:
                    raise Exception('LINK NOT VALID: "%s"' % link) # TODO: better Exception class
            value = link_target

        # the attribute_name might change because of an installed link
        many_for_one_lookup = None
        if attribute_name in self.__dict__['_many_for_one']:
            many_for_one_lookup = self.__dict__['_many_for_one'][attribute_name]

        if isinstance(self.get_kwarg('available_settings').get(attribute_name, None), dict) or (
            many_for_one_lookup is not None and
            isinstance(self.get_kwarg('available_settings').get(many_for_one_lookup, None), dict)
        ):
            if isinstance(value, (tuple, list)):
                if len(value) and not isinstance(value[0], SettingsWrapper):
                    new_value = value.__class__()
                    for val in value:
                        new_value += value.__class__(
                            (self.as_wrapped(
                                attribute_name=(many_for_one_lookup or attribute_name),
                                value=val
                            ), )
                        )
                    value = new_value
            elif not isinstance(value, SettingsWrapper):
                value = self.as_wrapped(
                    attribute_name=attribute_name,
                    value=value
                )

        if many_for_one_lookup is not None and not isinstance(value, (tuple, list)):
            value = [value]

        # apply filter if needed
        if isinstance(value, (list, tuple)) and filter:
            for target in value:
                if getattr(target, filter, None) == filter_value:
                    value = target
                    break

        if attribute_name in self.get_kwarg('import_strings') and isinstance(attribute_name, basestring):
            value = perform_import(
                self.__dict__['_config'].get('NAME'),
                value,
                ((self.get_kwarg('lookup_path') + '.') if self.get_kwarg('lookup_path') else '') + attribute_name
            )

        for lookup in [attribute_name, many_for_one_lookup]:
            if lookup in self.get_kwarg('init'):
                value = perform_init(
                    self.__dict__['_config'].get('NAME'),
                    value,
                    ((self.get_kwarg('lookup_path') + '.') if self.get_kwarg('lookup_path') else '') + lookup,
                    self.get_kwarg('init')[lookup]
                )
                break

        return value

    def raise_attribute_error(self, **kwargs):
        if 'settings_name' not in kwargs:
            kwargs['settings_name'] = self.__dict__['_config'].get('NAME')
        if 'lookup_path' not in kwargs:
            kwargs['lookup_path'] = ('.' + self.get_kwarg('lookup_path')) if self.get_kwarg('lookup_path') else ''
        raise Exception("Invalid '{settings_name}{lookup_path}' setting: '{attribute_name}'".format(**kwargs))

    def configure(self, configuration):
        # TODO: maybe need better configuration possibilities?
        self.get_kwarg('configuration').update(configuration)

    def with_configuration(self, configuration):
        new_wrapper = self.as_wrapped()
        new_wrapper.configure(configuration)
        return new_wrapper

    def as_wrapped(self, **kwargs):
        return self.get_wrapper_class()(**self.get_wrapped_kwargs(**kwargs))

    def get_wrapped_kwargs(self, **kwargs):
        attribute_name = kwargs.get('attribute_name', None)
        if attribute_name and attribute_name in self.__dict__['_many_for_one']:
            attribute_name = self.__dict__['_many_for_one'].get(attribute_name)
        if attribute_name:
            kwargs['attribute_name'] = attribute_name

        new_kwargs = {
            'config': self.__dict__['_config'],
            'settings': self.__dict__['_dict'].get(attribute_name, None) if attribute_name else self.__dict__['_dict'],
        }
        for kwarg in self.__dict__['_kwargs'].keys():
            if kwarg not in ['config', 'settings']:
                new_kwargs[kwarg] = self.wrap_own_kwargs(kwarg, **kwargs)

        return new_kwargs

    def wrap_own_kwargs(self, name, **kwargs):
        attribute_name = kwargs.get('attribute_name', None)
        #if attribute_name in self.get_kwarg('links'):
        #    link = self.get_kwarg('links')[attribute_name].split('|')[0]
        #    current_value = app_settings(self.__dict__['_config']).get_kwarg(link)
        #else:
        current_value = self.get_kwarg(name)
        found = False

        if name in ['defaults', 'available_settings', 'configuration']:
            if attribute_name:
                return current_value.get(attribute_name, None)
            found = True
        elif name in ['import_strings']:
            if attribute_name:
                prefix = (attribute_name + '.') if attribute_name else None
                return (string[len(prefix):] for string in current_value if string.startswith(prefix))
            found = True
        elif name in ['one_to_many', 'links', 'init']:
            if attribute_name:
                prefix = (attribute_name + '.') if attribute_name else None
                new_dict = {}
                for key, value in current_value.items():
                    add = False
                    if key.startswith(prefix):
                        add = True
                        key = key[len(prefix):]
                    if value.startswith(prefix):
                        # only if its one_to_many kwarg, the value may cause an inheritance to the next wrapper
                        add = name in ['one_to_many']
                        value = value[len(prefix):]
                    if add:
                        new_dict[key] = value

                return new_dict
            found = True
        elif name == 'parent_settings':
            if attribute_name:
                return getattr(current_value, attribute_name, None)
            found = True
        elif name == 'lookup_path':
            if attribute_name:
                return ((current_value + '.') if current_value else '') + attribute_name
            found = True
        elif name == 'upper_settings':
            if attribute_name:
                return self
            found = True

        if found:
            return current_value

        return None

    def get_kwarg(self, name):
        return self.__dict__['_kwargs'].get(name)

    def get_wrapper_class(self):
        return SettingsWrapper

"""
class ExampleSubclassWrapper(SettingsWrapper):
    def __init__(self, *args, my_var=None, **kwargs):
        super(ExampleSubclassWrapper, self).__init__(*args, **kwargs)
        self.__dict__['_kwargs']['_my_var'] = my_var

    def get_value(self, attribute_name):
        value = super(ExampleSubclassWrapper, self).get_value(attribute_name)

        if value is None:
            value = self.__dict__['_kwargs']['_my_var']

        return value

    def wrap_own_kwargs(self, name, **kwargs):
        found = False
        value = super(ExampleSubclassWrapper, self).wrap_own_kwargs(name, **kwargs)

        if value is None and name == 'my_var':
            attribute_name = kwargs.get('attribute_name')
            if attribute_name:
                return self.__dict__['_kwargs']['_my_var'] + '-' + attribute_name
            found = True

        if found:
            return self.get_kwarg(name)

        return value

    def get_wrapper_class(self):
        return ExampleSubclassWrapper
"""


def app_settings(app_config, parent_settings=None, configuration=None):
    settings_name = app_config.get('NAME')
    if settings_name is None:
        raise Exception('app_config.NAME should be defined')

    # TODO: check, that nothing insinde IMPORT_SETTINGS is represened by a dict in SETTINGS

    wrapper = SettingsWrapper(
        config=app_config,
        settings=getattr(settings, settings_name, None),
        parent_settings=parent_settings,
        available_settings=app_config.get('SETTINGS', None),
        defaults=app_config.get('DEFAULTS', None),
        import_strings=app_config.get('IMPORT_STRINGS', None),
        one_to_many=app_config.get('ONE_TO_MANY', None),
        validation_method=app_config.get('VALIDATION_METHOD', None),
        links=app_config.get('LINK', None),
        init=app_config.get('INIT', None),
        configuration=configuration
    )

    return wrapper
