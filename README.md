# IceLevel

RPG-трекер тренировок для хоккеистов-любителей. См. `docs/hockeylevelup_final_concept.md`
и `docs/hockeylevelup_dev_plan.md`.

## Запуск через Docker (весь стек)

```bash
cp .env.example .env
docker compose up -d --build
```

Поднимает postgres, rabbitmq, backend (FastAPI, автоматически применяет
`alembic upgrade head` при старте, `--reload` внутри контейнера) и frontend
(Vite dev server). Исходники бэкенда и фронтенда смонтированы внутрь
контейнеров, так что правки на хосте подхватываются на лету, без пересборки
образа -- пересобирать (`--build`) нужно только после изменения
`pyproject.toml`/`poetry.lock` или `frontend/package.json`.

- Backend: http://localhost:8000 (документация — http://localhost:8000/docs)
- Frontend: http://localhost:5173
- RabbitMQ management UI: http://localhost:15672 (guest/guest)

`docker compose logs -f backend` / `frontend` — смотреть логи. `docker compose
down` — остановить (данные Postgres остаются в volume `postgres_data`).

## Локальный запуск без Docker для backend/frontend (Фаза 0)

```bash
cp .env.example .env
docker compose up -d postgres rabbitmq
poetry install
poetry run alembic upgrade head
poetry run uvicorn app.main:app --reload --host 0.0.0.0
```

API документация: http://127.0.0.1:8000/docs

`--host 0.0.0.0` binds every network interface, not just loopback -- needed so
a phone on the same Wi-Fi can reach the API via the PC's LAN IP. Drop it
(defaults to 127.0.0.1) if you only ever access the API from this machine.

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
