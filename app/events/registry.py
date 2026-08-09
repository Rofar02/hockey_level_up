import uuid
from collections import defaultdict
from collections.abc import Awaitable, Callable

Handler = Callable[[dict, uuid.UUID], Awaitable[None]]

_handlers: dict[str, list[Handler]] = defaultdict(list)


def register_handler(event_type: str) -> Callable[[Handler], Handler]:
    def decorator(func: Handler) -> Handler:
        _handlers[event_type].append(func)
        return func

    return decorator


def get_handlers(event_type: str) -> list[Handler]:
    return list(_handlers.get(event_type, []))
