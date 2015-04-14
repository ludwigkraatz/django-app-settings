import logging
from django.conf import settings
from django.utils.functional import LazyObject, empty
from django.utils import importlib
from .init import get_instance, get_wrapped_instance
from .exceptions import InvalidSettingError
from .utils import dict_merge


def perform_import(settings_name, val, setting_lookup):
    """
    If the given setting is a string import notation,
    then perform the necessary import or imports.
    """
    if not val:
        return None
    if isinstance(val, basestring):
        return import_from_string(settings_name, val, setting_lookup)
    elif isinstance(val, (list, tuple)):
        return [import_from_string(settings_name, item, setting_lookup) for item in val]
    elif isinstance(val, dict):
        ret = {}
        for key, value in val.items():
            ret[key] = import_from_string(settings_name, value, setting_lookup)
        val = ret
    return val


def perform_init(settings_name, val, setting_lookup, init_method):
    #init_method = import_from_string(settings_name, init_method_location, setting_lookup, 'init')
    if not callable(init_method):
        raise Exception('init method "%s" is not callable' % init_method)  # TODO: better class

    if isinstance(val, (tuple, list)):
        ret = val.__class__()

        for current_val in val:
            if not isinstance(current_val, (basestring, dict, SettingsWrapper)):
                return val
            instance = init_method(current_val)
            ret += val.__class__((instance, ))

        return ret
    elif isinstance(val, dict):
        ret = {}
        for key, value in val.items():
            ret[key] = init_method(value)
        val = ret

    if not isinstance(val, (SettingsWrapper)):
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


class SettingsHolder(object):
    def __init__(self, wrapped):
        self.__wrapped = wrapped

    @property
    def _wrapped(self):
        return self.__wrapped

    @_wrapped.setter
    def _wrapped(self, wrapped):
        self.__wrapped = wrapped

    def __getattr__(self, name):
        return getattr(self._wrapped, name)


class SettingsWrapper(object):
    def __init__(self, config=None, settings=None, available_settings=None, import_strings=None, validation_method=None,
                 one_to_many=None, parent_settings=None, defaults=None, configuration=None, lookup_path=None,
                 links=None, init=None, upper_setting=None, global_settings=None,
                 resolving_link=False, parent_setting=None, **kwargs):
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
            target, filter = self.unpack_filter(value)
            self.__dict__['_many_for_one'][target] = '|'.join((key, filter) if filter else (key, ))

        self.__dict__['_kwargs']['parent_settings'] = parent_settings or None  # is accessed with getattr()
        self.__dict__['_kwargs']['defaults'] = defaults or {}
        self.__dict__['_kwargs']['global_settings'] = global_settings or []

        self.__dict__['_kwargs']['upper_setting'] = upper_setting
        self.__dict__['_kwargs']['resolving_link'] = resolving_link
        self.__dict__['_kwargs']['parent_setting'] = parent_setting

        self.__dict__['_kwargs']['links'] = links or {}
        self.__dict__['_kwargs']['init'] = init or {}

        self.__dict__['_kwargs']['configuration'] = None
        if configuration:
            self.configure(configuration)

    def unpack_filter(self, value):
        if value and '|' in value:
            return value.split('|')
        else:
            return value, None

    def as_dict(self):
        return self.__dict__['_dict']

    def deprecation_warning(self, attribute_name, message=None):
        pass  # TODO: implement deprecation warning for settings wrapper

    def get_active_configuration(self):
        return self.get_kwarg('configuration')

    def link_resolved(self):
        self.__dict__['_kwargs']['resolving_link'] = False

    def get_configuration_value(self, attribute_name):
        value = None
        configuration = self.get_active_configuration()
        if configuration is not None:
            value = configuration.get(attribute_name, configuration['.'].get(attribute_name, None))
        return value

    def get_configuration(self, attribute_name=None, lookup_value=None, many_for_one_filter=None):
        value = None
        configuration = self.get_active_configuration()
        if configuration is not None:
            value = {'.': configuration['.']}
            found = False
            if attribute_name and attribute_name in configuration:
                found = True
                value.update(configuration.get(attribute_name, {}))
            if isinstance(lookup_value, dict) and many_for_one_filter in lookup_value:
                # this should handle COLLECTION[{'MANY_TO_MANY_FILTER': 'real_lookup_value', ...}['MAN..']]
                real_lookup_value = lookup_value.get(many_for_one_filter)
                found = True
                if real_lookup_value not in configuration and (attribute_name + '_COLLECTION') in configuration:
                    _conf = configuration[attribute_name + '_COLLECTION']
                else:
                    _conf = configuration
                if real_lookup_value in _conf:
                    value.update(_conf.get(real_lookup_value, {}))
            elif isinstance(lookup_value, basestring) and lookup_value in configuration:
                # this should handle COLLECTION[lookup_value]
                found = True
                value.update(configuration.get(lookup_value, {}))
            if not found:
                value.update(configuration['.'])
        return value

    def get_value(self, attribute_name):
        many_for_one_lookup, many_for_one_filter = self.unpack_filter(self.__dict__['_many_for_one'].get(attribute_name, None))
        wrap_one_to_many = False
        value = self.get_configuration_value(attribute_name)
        if isinstance(value, dict):
            value = None

        if value is None:
            value = self.__dict__['_dict'].get(attribute_name, None)

        if value is None and self.get_kwarg('parent_settings') is not None:
            value = getattr(self.get_kwarg('parent_settings'), attribute_name, None)

        if value is None and many_for_one_lookup:
            value = self.get_value(many_for_one_lookup)
            #value = self.__getattr__(many_for_one_lookup)
            wrap_one_to_many = True

        # wrap one into Collection/List
        try:
            if wrap_one_to_many:
                if many_for_one_filter:
                    ret = {}
                    if value:
                        if many_for_one_filter not in value:
                            raise InvalidSettingError(many_for_one_filter, value)
                        value_lookup = value.get(many_for_one_filter)
                        value.update(self.get_configuration(value_lookup) or {})
                        ret[value_lookup] = value
                    value = ret
                elif not isinstance(value, (tuple, list)):
                    value = [value]
        except InvalidSettingError:
            value = None  # this means, its a default value thats not relevant here

        if many_for_one_lookup == 'DEPENDS_ON':
            raise Exception(value)
        # update defaults

        if True:
            parent_value = None
            if value is None and attribute_name in self.list_globals():
                if self.get_kwarg('parent_setting') and hasattr(self.get_kwarg('parent_setting'), attribute_name):
                    parent_value = getattr(self.get_kwarg('parent_setting'), attribute_name)
                elif self.get_kwarg('upper_setting') and hasattr(self.get_kwarg('upper_setting'), attribute_name):
                    parent_value = getattr(self.get_kwarg('upper_setting'), attribute_name)

            default = self.get_kwarg('defaults').get(
                attribute_name
            )

            for default_value in [parent_value or default, ]:
                if default_value is not None:
                    if isinstance(value, dict) and isinstance(default_value, dict):
                        ret = {}
                        for key, val in default_value.items():
                            if isinstance(val, dict):
                                if key in value and val.get('_PROTECTED_'+key, False):
                                    raise Exception('protected DEFAULT Value "%s" can\'t be overwritten.' % (key))

                                if key in value and val.get('PROTECTED', False) and any(v in value[key] for v in val.keys() if v != many_for_one_filter):
                                    raise Exception('protected DEFAULT setting item "%s" can\'t be overwritten.' % (key))

                            ret[key] = val
                        for key, val in value.items():
                            ret[key] = dict_merge(ret.get(key, {}), val)
                        value = ret
            if value is None:
                value = parent_value or default

        return value

    def list_available_attributes(self):
        available_settings = {}

        # TODO: self.get_absolute_lookup(settings_name=False) in self.get_kwargs('init'): append 'CLASS'/'_INIT_METHOD'
        default_attributes = ['PROTECTED', 'CLASS']
        default_attributes += self.list_globals()

        for key, value in self.get_kwarg('available_settings').items():
            available_settings[key] = value
        for key in default_attributes:
            available_settings[key] = None

        return available_settings

    def list_import_targets(self):
        default_targets = ['_INIT_METHOD', 'CLASS']
        return self.get_kwarg('import_strings') + default_targets

    def list_globals(self):
        default_globals = ['DEBUG', '_INIT_METHOD']
        return self.get_kwarg('global_settings') + default_globals

    def get_absolute_lookup(self, attribute_name, include_settings_name=True):
        return (
            (self.__dict__['_config'].get('NAME') + '.')
            if include_settings_name else
            '') + (
                (self.get_kwarg('lookup_path') + '.')
                if self.get_kwarg('lookup_path')
                else ''
            ) + attribute_name

    def __getattr__(self, name):
        """
            getattr method of settings wrapper has just one porpuse:
            allow nested settings access
            TODO: is this usefull?
        """
        settings = name.split('.')
        obj = self
        for setting_name in settings:
            obj = obj.get_attribute(setting_name)
        return obj

    def get_attribute(self, name, filter=None, filter_value=None):
        # shortcuts
        if name == '_PARENT':
            return self.get_kwarg('parent_setting')
        if name == '_INSTANCE':
            return self._INIT_METHOD(self)

        # test if requested attribute is available
        available_attributes = self.list_available_attributes()
        if name not in available_attributes:
            self.raise_error(
                AttributeError,
                attribute_name=name
            )  # TODO: maybe raise SettingNotAvailable or similar
        if ('_DEPRECATED_' + name) in available_attributes:
            self.deprecation_warning(name, available_attributes['_DEPRECATED_' + name])

        # get value
        value = self.get_value(name)

        # validate value  # TODO: do this when writing a configuration / loading settings
        if value is None:
            self.raise_error(
                attribute_name=name
            )
        validation_method = None
        if ('_VALIDATE_' + name) in self.__dict__['_dict']:
            validation_method = perform_import(
                self.get_absolute_lookup(name),
                self.__dict__['_dict']['_VALIDATE_' + name],
                '_VALIDATE_' + name
            )
        elif self.get_kwarg('validation_method') is not None:
            validation_method = perform_import(
                self.get_absolute_lookup(name),
                self.get_kwarg('validation_method'),
                'validation_method'
            )
        if validation_method is not None and False:  # TODO
            if not validation_method(name, value):
                self.raise_error(
                    attribute_name=name
                )  # TODO: maybe raise SettingsInvalid or similar

        # finalize the value: imports / init / ...
        value = self.finalize_value(name, value, filter, filter_value)

        # cache for next access and return
        setattr(self, name, value)
        return value

    def get_filtered(self, attribute_name, filter, filter_value):
        # TODO: getattr, because of nested attribute_name
        if not isinstance(filter_value, basestring):
            raise Exception(attribute_name, filter, filter_value.__dict__)
        return self.get_attribute(attribute_name, filter, filter_value)

    def finalize_value(self, attribute_name, value, filter, filter_value):
        many_for_one_lookup, many_for_one_filter = self.unpack_filter(self.__dict__['_many_for_one'].get(attribute_name, None))
        configuration = (self.get_active_configuration() or {'.': None}).get('.')
        if many_for_one_filter:
            conf = self.get_configuration(many_for_one_filter=many_for_one_filter)
            if conf and not isinstance(configuration, dict):
                configuration = conf
            elif conf:
                configuration.update(conf)

        # handle links
        target = None
        link = self.get_kwarg('links').get(attribute_name, None) or self.get_kwarg('links').get(many_for_one_lookup, None)
        if link and isinstance(value, (list, tuple, basestring)):
            target, filter = self.unpack_filter(link)

            new_config = self.__dict__['_config']
            resolving_link_for = self  # no: self.get_kwarg('parent_setting') if self.get_kwarg('resolving_link') else
            if isinstance(value, (list, tuple)):
                link_target = value.__class__()
                for temp_value in value:
                    temp_target = app_settings(
                        new_config,
                        resolving_link_for=resolving_link_for,
                        configuration=configuration,
                        in_holder=False
                    ).get_filtered(target, filter, temp_value)
                    if not temp_target:
                        temp_target = self.get_filtered(target, filter, temp_value)
                    if not temp_target:
                        raise Exception('LINK NOT VALID: "%s"' % link) # TODO: better Exception class
                    temp_target.link_resolved()
                    link_target += value.__class__([temp_target, ])
            else:
                link_target = app_settings(
                    new_config,
                    resolving_link_for=resolving_link_for,
                    configuration=configuration,
                    in_holder=False
                ).get_filtered(target, filter, value)
                if link_target is None:
                    link_target = self.get_filtered(target, filter, value)
                if not link_target:
                    raise Exception('LINK NOT VALID: "%s"' % link) # TODO: better Exception class
                link_target.link_resolved()

            value = link_target
        # wrap child settings (but no collections!)
        if (
            attribute_name.endswith('_COLLECTION') or
            (many_for_one_lookup and many_for_one_lookup.endswith('_COLLECTION'))
        ):
            if isinstance(value, dict):
                ret = {}
                for key, val in value.items():
                    ret[key] = self.as_wrapped(
                        attribute_name=(many_for_one_lookup or attribute_name),
                        value=val,
                        many_for_one_filter=many_for_one_filter
                    )
                value = ret
        elif (

            isinstance(self.get_kwarg('available_settings').get(attribute_name, None), dict)
        ) or (
            many_for_one_lookup and
            isinstance(self.get_kwarg('available_settings').get(many_for_one_lookup, None), dict)
        ):
            if isinstance(value, (tuple, list)):
                if len(value) and not isinstance(value[0], SettingsWrapper):
                    new_value = value.__class__()
                    for val in value:
                        new_value += value.__class__(
                            (self.as_wrapped(
                                attribute_name=(many_for_one_lookup or attribute_name),
                                value=val,
                                many_for_one_filter=many_for_one_filter
                            ), )
                        )
                    value = new_value
            elif not isinstance(value, SettingsWrapper):
                value = self.as_wrapped(
                    attribute_name=attribute_name,
                    value=value,
                    many_for_one_filter=many_for_one_filter
                )

        # apply filter if needed
        if filter_value:
            matched = False
            if isinstance(value, (list, tuple)) and value and filter:
                for target in value:
                    if getattr(target, filter, None) == filter_value:
                        new_value = target
                        matched = True
                        break
            elif isinstance(value, dict) and value:
                new_value = value.get(filter_value, None)
                matched = new_value is not None
            if not matched:
                raise Exception('filter "%s" not matched. found %s' % (filter_value, str(value)))
            value = new_value

        # import
        if attribute_name in self.list_import_targets() and isinstance(attribute_name, basestring):  # Note: i think the isinstance check is useless and should be removed: TODO
            value = perform_import(
                self.__dict__['_config'].get('NAME'),
                value,
                self.get_absolute_lookup(attribute_name)
            )

        # init
        for lookup in [attribute_name, many_for_one_lookup]:
            if lookup in self.get_kwarg('init'):
                value = perform_init(
                    self.__dict__['_config'].get('NAME'),
                    value,
                    self.get_absolute_lookup(lookup),
                    self._INIT_METHOD
                )
                break

        return value

    def raise_error(self, exception_class=InvalidSettingError, **kwargs):
        attribute_name = kwargs.pop('attribute_name')
        if 'lookup_path' not in kwargs:
            kwargs['lookup_path'] = self.get_absolute_lookup(attribute_name)
        raise exception_class("Invalid setting '{lookup_path}'".format(**kwargs))

    def configure(self, configuration):
        _configuration = self.get_active_configuration()
        if _configuration is None:
            self.__dict__['_kwargs']['configuration'] = {'.': {}}
            _configuration = self.__dict__['_kwargs']['configuration']

        if isinstance(configuration, SettingsWrapper):
            configuration = configuration.as_dict()

        if '.' in configuration:
            _configuration['.'] = configuration['.']
        else:
            configuration['.'] = configuration
        _configuration.update(configuration)

    def with_configuration(self, configuration):
        new_wrapper = self.as_wrapped()
        new_wrapper.configure(configuration)
        return new_wrapper

    def as_wrapped(self, **kwargs):
        return self.get_wrapper_class()(**self.get_wrapped_kwargs(**kwargs))

    def get_wrapped_kwargs(self, **kwargs):
        attribute_name = kwargs.get('attribute_name', None)
        if attribute_name and attribute_name in self.__dict__['_many_for_one']:
            attribute_name = self.unpack_filter(self.__dict__['_many_for_one'].get(attribute_name))[0]
        if attribute_name:
            kwargs['attribute_name'] = attribute_name

        if 'value' in kwargs:
            settings = kwargs.get('value')
        else:
            settings = self.__dict__['_dict'].get(attribute_name, None) if attribute_name else self.__dict__['_dict']

        new_kwargs = {
            'config': self.__dict__['_config'],
            'settings': settings
        }
        for kwarg in self.__dict__['_kwargs'].keys():
            if kwarg not in ['config', 'settings']:
                new_kwargs[kwarg] = self.wrap_own_kwargs(kwarg, **kwargs)

        return new_kwargs

    def wrap_own_kwargs(self, name, **kwargs):
        attribute_name = kwargs.get('attribute_name', None)
        value = kwargs.get('value', None)
        many_for_one_filter = kwargs.get('many_for_one_filter', None)
        #if attribute_name in self.get_kwarg('links'):
        #    link = self.unpack_filter(self.get_kwarg('links')[attribute_name])[0]
        #    current_value = app_settings(self.__dict__['_config']).get_kwarg(link)
        #else:
        current_value = self.get_kwarg(name)

        found = False
        if name in ['defaults', 'available_settings', 'configuration']:
            if name == 'configuration':
                current_value = self.get_configuration(attribute_name, lookup_value=value, many_for_one_filter=many_for_one_filter)
            elif attribute_name:
                return current_value.get(attribute_name, None)
            found = True
        elif name in ['import_strings', 'init']:
            if attribute_name:
                prefix = attribute_name + '.'
                return (string[len(prefix):] for string in current_value if string.startswith(prefix))
            found = True
        elif name in ['one_to_many', 'links']:
            if attribute_name:
                prefix = (attribute_name + '.')
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
        elif name == 'parent_settings':# TODO: is this correct?
            if attribute_name:
                return getattr(current_value, attribute_name, None)
            found = True
        elif name == 'lookup_path':
            if attribute_name:
                return ((current_value + '.') if current_value else '') + attribute_name
            found = True
        elif name == 'upper_setting':
            if attribute_name:
                return self
            found = True
        elif name == 'parent_setting':
            if attribute_name:
                if self.get_kwarg('resolving_link'):
                    return current_value
                return self
            found = True
        elif name in ['global_settings']:
            found = True

        if found:
            return current_value

        return None

    def get_kwarg(self, name):
        return self.__dict__['_kwargs'].get(name)

    def get_wrapper_class(self):
        return SettingsWrapper

    def __str__(self, ):
        return 'SettingsWrapper: config=%s' % self.__dict__['_dict']

    def __hash__(self):
        return hash(str(self.__dict__['_dict']))  # TODO: find better hash source

    def __unicode__(self, ):
        return self.__str__()

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


def app_settings(app_config, parent_settings=None, configuration=None, resolving_link_for=None, in_holder=True):
    settings_name = app_config.get('NAME')
    if settings_name is None:
        raise Exception('app_config.NAME should be defined')

    # TODO: check, that nothing insinde IMPORT_SETTINGS is represened by a dict in SETTINGS

    app_settings = getattr(settings, settings_name, None)
    one_to_many = app_config.get('ONE_TO_MANY', None)
    if one_to_many:
        _configuration = {}
        for key in one_to_many:
            if '.' in key:
                continue
            if not key in app_settings:
                continue

            _configuration[key] = app_settings[key]
        if configuration:
            _configuration.update(configuration)
        configuration = _configuration

    wrapped = SettingsWrapper(
        config=app_config,
        settings=app_settings,
        parent_settings=parent_settings,
        available_settings=app_config.get('SETTINGS', None),
        defaults=app_config.get('DEFAULTS', None),
        import_strings=app_config.get('IMPORT_STRINGS', None),
        one_to_many=one_to_many,
        validation_method=app_config.get('VALIDATION_METHOD', None),
        links=app_config.get('LINK', None),
        init=app_config.get('INIT', None),
        global_settings=app_config.get('GLOBALS'),
        configuration=configuration,
        parent_setting=resolving_link_for,
        resolving_link=bool(resolving_link_for)
    )
    if not in_holder:
        return wrapped

    wrapper = SettingsHolder(wrapped)

    return wrapper
