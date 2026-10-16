"""`?optional=1` on the "nothing yet" reads (15.10).

A new player has no week, no training block and no day plans yet; the app
asks anyway on every start, and every 404 lands in the browser console as a
red "Failed to load resource" line. With `optional=1` such a read answers
200 with `null` instead. Without the flag nothing changes: installed phones
still on an older build keep getting the 404 they handle.
"""
from collections.abc import Awaitable
from typing import Annotated, TypeVar

from fastapi import HTTPException, Query, status

T = TypeVar("T")

OptionalFlag = Annotated[bool, Query(description="200 + null instead of 404 when there is nothing yet")]


async def or_none(read: Awaitable[T], optional: bool) -> T | None:
    try:
        return await read
    except HTTPException as exc:
        if optional and exc.status_code == status.HTTP_404_NOT_FOUND:
            return None
        raise
