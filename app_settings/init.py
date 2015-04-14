
_instance_storage = {}


def storage_instance(hash_value, instance=None):
    if instance is None:
        return _instance_storage.get(hash_value, None)

    _instance_storage[hash_value] = instance


def get_instance(config):
    if not hasattr(config, 'CLASS'):
        raise Exception('config "%s" should be a SettingsWrapper with "CLASS" attribute not "%s" instance' % (
            str(config),
            str(config.__class__)
        ))
    instance_class = config.CLASS
    hash_value = hash((instance_class, config))
    instance = storage_instance(hash_value)

    if instance is None:
        instance = instance_class(settings=config)
        storage_instance(hash_value, instance)

    return instance


def get_wrapped_instance(config):
    return ClassWrapper(get_instance(config), config)


def get_class_from_config(config):
    if isinstance(config, (tuple, list)):
        ret = config.__class__()

        for current_config in config:
            instance = get_instance(current_config)
            ret += config.__class__((instance, ))

        return ret

    instance = get_instance(config)
    return instance


def wrap_class_with_config(config):
    if isinstance(config, (tuple, list)):
        ret = config.__class__()

        for current_config in config:
            instance = get_wrapped_instance(current_config)
            ret += config.__class__((instance, ))

        return ret

    instance = get_wrapped_instance(config)
    return instance


class Empty(object):
    pass


class ClassWrapper(object):
    def __init__(self, instance, config):
        self.__instance = instance
        self.__config = config

        for attr in self.__config.__dict__['_dict'].keys():
            if hasattr(self.__instance, attr):
                raise Exception('can\'t wrap class"%s" with this config. \
                    Attribute "%s" found in both.' % (
                    str(instance.__class__),
                    attr
                ))

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return self.__instance == other.__instance
        return self.__instance == other

    def __ne__(self, other):
        return not self.__eq__(other)

    def __getattr__(self, attr):
        # at least one of te two following is always None
        config_value = getattr(self.__config, attr, Empty)
        instance_value = getattr(self.__instance, attr, Empty)

        if config_value is not Empty:
            return config_value
        if instance_value is not Empty:
            return instance_value
        raise AttributeError('Attribute "%s" not found in config/instance' % attr)

    def __str__(self, ):
        return 'ClassWrapper: instance=%s (%s)' % (self.__instance, self.__config)

    def __unicode__(self, ):
        return self.__str__()
