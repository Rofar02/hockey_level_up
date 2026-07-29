# HockeyLevelUp

RPG-трекер тренировок для хоккеистов-любителей. См. `docs/hockeylevelup_final_concept.md`
и `docs/hockeylevelup_dev_plan.md`.

## Локальный запуск (Фаза 0)

```bash
cp .env.example .env
docker compose up -d postgres rabbitmq
poetry install
poetry run alembic upgrade head
poetry run uvicorn app.main:app --reload
```

API документация: http://127.0.0.1:8000/docs

### Auth

- `POST /auth/register` — регистрация (username, email, password, height, weight, age, position, years_of_experience).
- `POST /auth/login` — логин (form-data: username, password) → access + refresh токены.
- `POST /auth/refresh` — обновление пары токенов по refresh-токену.
- `GET /auth/me` — текущий пользователь (Bearer access token).

### Миграции

```bash
poetry run alembic revision --autogenerate -m "message"
poetry run alembic upgrade head
```
