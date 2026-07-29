import enum
from typing import TypeVar

from sqlalchemy import Enum

E = TypeVar("E", bound=enum.StrEnum)


def enum_column(enum_cls: type[E], name: str) -> Enum:
    """VARCHAR-backed enum column: portable across DBs, validated at the app layer."""
    return Enum(
        enum_cls,
        name=name,
        native_enum=False,
        values_callable=lambda cls: [member.value for member in cls],
    )
