from fastapi import FastAPI

from app.core.config import get_settings
from app.routers import auth, exercises, schedule, users

settings = get_settings()

app = FastAPI(title=settings.app_name)

app.include_router(auth.router)
app.include_router(exercises.router)
app.include_router(users.router)
app.include_router(schedule.router)


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
