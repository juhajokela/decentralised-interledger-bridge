import asyncio
import inspect

from datetime import datetime
from hashlib import sha256


def generate_hash_id(seed: str, salt: str) -> str:
    hash = sha256((seed + salt).encode('utf-8')).hexdigest()
    return str(int(f'0x{hash}', 0))


class Logger:

    log_line_number = 1

    @classmethod
    def init(cls, node_id):
        cls.node_id = node_id

    @classmethod
    def log(cls, *args, important=False):
        include = [
            '*',
        ]
        exclude = [
        ]

        frame = inspect.stack()[1]
        func = frame.function
        module = inspect.getmodule(frame[0]).__name__.split('.')[-1]
        condition = include and (func not in exclude) and (('*' in include) or (func in include))

        if condition or important:
            print(
                getattr(cls, 'node_id', ''),
                cls.log_line_number,
                datetime.utcnow().strftime('%m/%d %H:%M:%S.%f')[:-3],
                module.ljust(15),
                func.ljust(25),
                *args,
                flush=True
            )
            cls.log_line_number += 1
