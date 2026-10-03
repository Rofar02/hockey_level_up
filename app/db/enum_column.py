import enum
from typing import TypeVar

from sqlalchemy import Enum

E = TypeVar("E", bound=enum.StrEnum)


def enum_column(enum_cls: type[E], name: str, length: int | None = None) -> Enum:
    """VARCHAR-backed enum column: portable across DBs, validated at the app layer.

    `length` pins the VARCHAR size. Without it SQLAlchemy sizes the column to
    the longest value at table-creation time, so a later, longer enum value
    (e.g. muscle group "hip_flexors" after "hamstrings") would not fit the
    existing column -- pin a roomy length where the enum is expected to grow.
    """
    return Enum(
        enum_cls,
        name=name,
        native_enum=False,
        length=length,
        values_callable=lambda cls: [member.value for member in cls],
    )
