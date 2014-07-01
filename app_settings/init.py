
def get_class_from_config(config):
    if isinstance(config, (tuple, list)):
        ret = config.__class__()
        for storage_config in config:
            ret += config.__class__((storage_config.CLASS(storage_config), ))
        return ret
    return config.CLASS(settings=config)
