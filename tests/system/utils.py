import json


def json_default_serializer(obj):
    if isinstance(obj, (date, datetime, time)):
        return obj.isoformat()
    elif isinstance(obj, Decimal):
        return str(obj)
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


JSON_DEFAULT_SERIALIZER = json_default_serializer


def file_read(file_path):
    with open(file_path) as file:
        return file.read()


def file_write(file_path, data):
    with open(file_path, 'w') as file:
        file.write(data)


def json_read(file_path):
    return json.loads(file_read(file_path))


def json_write(file_path, data, **kwargs):
    kw = {
        'default': JSON_DEFAULT_SERIALIZER,
        **kwargs
    }
    file_write(file_path, json.dumps(data, **kw))

