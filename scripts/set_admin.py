"""One-off script: promote a user to admin by username.

Not an API endpoint -- console-only, for initial admin bootstrap:

    poetry run python scripts/set_admin.py <username>
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.db.session import AsyncSessionLocal  # noqa: E402
from app.models.user import User  # noqa: E402


async def set_admin(username: str) -> None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.username == username))
        user = result.scalar_one_or_none()
        if user is None:
            print(f"No user with username={username!r}")
            return
        if user.is_admin:
            print(f"{username} is already an admin")
            return

        user.is_admin = True
        await session.commit()
        print(f"{username} is now an admin (is_admin=True)")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: poetry run python scripts/set_admin.py <username>")
        sys.exit(1)
    asyncio.run(set_admin(sys.argv[1]))
