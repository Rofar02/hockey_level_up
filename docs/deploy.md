# Продакшен-деплой (icelevel.ru)

Раннбук для первого разворачивания на чистом Ubuntu-сервере и для последующих
обновлений через `git pull`. Архитектура: один edge-nginx на 80/443
(TLS + маршрутизация по пути `/api/*` → backend, всё остальное → frontend),
`postgres`/`rabbitmq` без единого порта наружу, `certbot` для сертификатов.
Подробности решений — в `docker-compose.prod.yml` и `deploy/nginx/app.conf`
(комментарии там объясняют "почему", не только "что").

## 0. Что нужно до старта

- Домен `icelevel.ru` куплен (есть).
- Сервер на Timeweb, чистый Ubuntu (есть).
- Публичный GitHub-репозиторий — деплой-ключ не нужен, `git clone`/`git pull`
  по HTTPS работают без авторизации.

## 1. Первичная настройка сервера

Малоаудиторный деплой ("показываю единицам") — работаем целиком под
`root` с паролем, который сгенерировал Timeweb при создании сервера,
без отдельного пользователя и без SSH-закаливания. Это сознательное
временное упрощение, не забытая недоделка — см. секцию "Что отложено"
в конце документа для того, что стоит сделать перед реальным ростом
аудитории.

Зайти на сервер по SSH как `root` с этим паролем, скопировать
`deploy/server-setup.sh` (например, через `scp`, либо просто открыть
файл на GitHub и вставить содержимое через `nano`), затем:

```bash
chmod +x server-setup.sh
./server-setup.sh
```

Скрипт ставит только Docker + Compose plugin (и 2GB swap, если на
сервере ≤2GB RAM — иначе `npm run build` фронтенда может упасть по
памяти). Больше ничего не трогает: ни firewall, ни sshd_config, ни
отдельных пользователей.

## 2. DNS

У регистратора/в панели Timeweb добавить:

```
A    icelevel.ru       → <IP сервера>
A    www.icelevel.ru   → <IP сервера>
```

Подождать распространения, проверить: `dig icelevel.ru +short`.

## 3. Клонирование репозитория

Под `root`:

```bash
mkdir -p /opt/icelevel
git clone https://github.com/Rofar02/hockey_level_up.git /opt/icelevel
cd /opt/icelevel
chmod +x deploy/*.sh
```

(Важно клонировать именно в директорию `icelevel` — от её имени Docker Compose
выводит имя проекта, а `deploy/backup.sh` ссылается на volume'ы
`icelevel_avatars_data` и т.п. по этому имени.)

## 4. `.env` — секреты на сервере

`.env` в `.gitignore`, `git pull` его никогда не тронет — секреты и код
обновляются полностью независимо.

```bash
cp .env.prod.example .env
chmod 600 .env
nano .env
```

Сгенерировать значения для `JWT_SECRET_KEY`, `POSTGRES_PASSWORD`,
`RABBITMQ_PASSWORD` прямо на сервере (никогда не хранить их значения в
этом файле в репозитории — раньше здесь лежали конкретные готовые
секреты, они утекли в публичный репозиторий и **не считаются валидными**,
на новом сервере ставим новые):

```bash
openssl rand -base64 64 | tr -d '\n' && echo   # JWT_SECRET_KEY
openssl rand -hex 32 && echo                    # POSTGRES_PASSWORD
openssl rand -hex 32 && echo                    # RABBITMQ_PASSWORD
```

`POSTGRES_PASSWORD`/`RABBITMQ_PASSWORD` specifically as `-hex`, not
`-base64`: `docker-compose.prod.yml` interpolates them straight into
`DATABASE_URL`/`RABBITMQ_URL` (`postgresql+asyncpg://user:PASSWORD@host/db`)
without URL-escaping, so a `/` or `+` from base64 output silently breaks
the URL parser (seen live: RabbitMQ consumer failed to start with a
`port can't be converted to integer` error, no crash, just silently
disabled). Hex output (`0-9a-f`) can never contain a URL-special
character. `JWT_SECRET_KEY` never goes into a URL, base64 is fine there.

VAPID-пару (для push-уведомлений) сгенерировать отдельно (например,
`npx web-push generate-vapid-keys` локально) и вставить
`VAPID_PUBLIC_KEY`/`VAPID_PRIVATE_KEY`.

`RESEND_API_KEY` — вставить свой реальный ключ Resend (тот же, что
используется локально, либо новый — но см. шаг 9 про верификацию домена,
без неё письма реальным пользователям не дойдут). `POSTGRES_USER`,
`RABBITMQ_USER` можно оставить как в примере (`icelevel`).

Если храните эти значения где-то отдельно (менеджер паролей) — сохраните
их сейчас. Дальше они живут только в `.env` на сервере (в `.gitignore`,
`git pull` его не тронет) и, по желанию, в вашем секретном хранилище —
никогда в файлах репозитория.

## 5. Сертификат — bootstrap-фаза (курица и яйцо)

`deploy/nginx/app.conf` ссылается на файлы сертификата, которых ещё нет —
nginx с ним не запустится. Сначала поднимаем HTTP-only конфиг:

```bash
cp deploy/nginx/bootstrap.conf deploy/nginx/active.conf
docker compose -f docker-compose.prod.yml up -d nginx
```

Проверить, что `http://icelevel.ru` отвечает (текст про bootstrap). Затем
выпустить сертификат. Сервис `certbot` в `docker-compose.prod.yml`
объявлен со своим `entrypoint` (бесконечный цикл `certbot renew`, для
ежедневного автопродления) — он не читает аргументы командной строки,
поэтому без `--entrypoint "certbot"` контейнер вместо разовой выписки
просто запустит цикл продления навечно и зависнет:

```bash
docker compose -f docker-compose.prod.yml run --rm --entrypoint "certbot" certbot \
  certonly --webroot -w /var/www/certbot \
  -d icelevel.ru -d www.icelevel.ru \
  --email lexa95k@gmail.com --agree-tos --no-eff-email
```

Если всё же запустили без `--entrypoint` и контейнер висит в `docker ps`
дольше минуты — `docker stop <имя>` (он с `--rm`, удалится сам) и
перезапустить команду выше, уже с `--entrypoint`.

## 6. Сертификат — боевой конфиг

```bash
cp deploy/nginx/app.conf deploy/nginx/active.conf
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml restart nginx
```

Проверить `https://icelevel.ru` — должен открыться (пока пустая/базовая
страница фронтенда, БД ещё не засеяна).

## 7. Проверка бэкенда и миграций

```bash
docker compose -f docker-compose.prod.yml logs -f backend
```

Миграции (`alembic upgrade head`) применяются автоматически при старте
контейнера — смотреть здесь. Если контейнер уходит в crash-loop
(`restart: unless-stopped` будет пытаться снова и снова) — тут же видно,
на какой миграции упало.

## 8. Сидирование базы

Пустая прод-БД бесполезна без каталога упражнений/навыков. По порядку
(каждый скрипт идемпотентен — пропускает уже существующие записи, повторный
запуск ничего не сломает):

```bash
docker compose -f docker-compose.prod.yml exec backend python scripts/seed_exercises.py
docker compose -f docker-compose.prod.yml exec backend python scripts/seed_offseason_catalog_additions.py
docker compose -f docker-compose.prod.yml exec backend python scripts/retag_equipment_mistags.py
docker compose -f docker-compose.prod.yml exec backend python scripts/backfill_warmup_stages.py
docker compose -f docker-compose.prod.yml exec backend python scripts/backfill_coordination_patterns.py
docker compose -f docker-compose.prod.yml exec backend python scripts/seed_skills.py
docker compose -f docker-compose.prod.yml exec backend python scripts/seed_skill_tags.py
docker compose -f docker-compose.prod.yml exec backend python scripts/seed_skill_milestones_skating.py
docker compose -f docker-compose.prod.yml exec backend python scripts/seed_skill_milestones_phase7.py
docker compose -f docker-compose.prod.yml exec backend python scripts/seed_skill_shot_accuracy.py
docker compose -f docker-compose.prod.yml exec backend python scripts/seed_reference_articles.py
```

Порядок в первых четырёх командах важен: `seed_offseason_catalog_additions.py`
добавляет новые упражнения (должен идти после базового каталога),
`retag_equipment_mistags.py`/`backfill_warmup_stages.py` правят уже
существующие по имени строки, так что запускаются последними. Все скрипты
идемпотентны (пропускают уже существующее) — безопасно перезапускать при
повторном деплое, если каталог обновился.

Затем зарегистрировать свой аккаунт через сам сайт (`https://icelevel.ru`) и
назначить его админом:

```bash
docker compose -f docker-compose.prod.yml exec backend python scripts/set_admin.py <ваш_username>
```

## 9. Email (Resend) — реальная доставка

Пока домен `icelevel.ru` не верифицирован в Resend (SPF/DKIM DNS-записи,
настраивается в личном кабинете Resend), письма подтверждения/сброса пароля
реальным пользователям не долетают — `EMAIL_FROM_ADDRESS` с адресом на
`resend.dev` доставляет только на почту владельца аккаунта Resend. Логин не
блокируется отсутствием подтверждения почты, но сброс пароля без письма
недоступен. После верификации — `EMAIL_FROM_ADDRESS=IceLevel
<noreply@icelevel.ru>` уже стоит в `.env.prod.example`, просто убедиться, что
не забыли добавить DNS-записи у регистратора.

## 10. Бэкапы

```bash
crontab -e
```

Добавить:

```
0 3 * * * /opt/icelevel/deploy/backup.sh >> /var/log/icelevel-backup.log 2>&1
```

Сразу проверить руками, что `deploy/backup.sh` реально отрабатывает и файлы
появляются в `/var/backups/icelevel/` — не дожидаться первого 3:00 ночи.

## 11. Обновление сервера (обычный рабочий цикл)

Локально: разработка в этом репозитории, коммит, `git push`. На сервере:

```bash
cd /opt/icelevel
./deploy/deploy.sh
```

Делает `git pull --ff-only` + `docker compose up -d --build` + подчищает
старые образы + сразу показывает хвост логов backend (чтобы упавшая
миграция была видна сразу, а не через час).

## 12. Смок-тест после любого деплоя

- Регистрация нового аккаунта → подтверждение письма (если Resend уже
  верифицирован) → логин.
- Загрузка аватара (проверяет лимит `client_max_body_size 6m` и права на
  volume — если аплоад падает с ошибкой прав, см. комментарий в
  `Dockerfile.prod` про порядок `mkdir`+`chown` до volume).
- Прямой переход по ссылке вида `https://icelevel.ru/verify-email?token=x`
  (не через клик в приложении) — проверяет SPA fallback в
  `frontend/nginx-spa.conf`.
- `curl -I https://icelevel.ru/api/docs` → должен быть `404` (закрыто в
  `deploy/nginx/app.conf`).
- Со своей машины: `nmap <IP сервера>` — снаружи должны быть видны только
  22/80/443, не 5432/5672/15672.

## Продление сертификата

Отдельный `certbot`-контейнер сам перепроверяет раз в сутки и продлевает
при необходимости (см. `docker-compose.prod.yml`) — ручных действий не
требует. nginx подхватывает новый сертификат при рестарте контейнера;
поставить в тот же cron ежемесячный `docker compose -f
docker-compose.prod.yml restart nginx`, если не хочется следить вручную.

## Что отложено (сознательно, не забыто)

Текущий деплой рассчитан на "показываю единицам", не на публичный рост
аудитории. Прежде чем звать больше пользователей — вернуться к этому:

- **SSH только по паролю root.** Нет ни ключей, ни отдельного
  пользователя, ни fail2ban/ufw. Приемлемо, пока сервер не боевой для
  посторонних; для реального продакшена — key-only SSH + отдельный
  deploy-пользователь + firewall.
- **Секреты, утёкшие в публичный репозиторий** (коммит `a26d17c`,
  прежняя версия этого файла) — `JWT_SECRET_KEY`, `POSTGRES_PASSWORD`,
  `RABBITMQ_PASSWORD`, `VAPID_PRIVATE_KEY` — считать скомпрометированными
  навсегда (публичная git-история не переписывалась). Секция 4 теперь
  генерирует новые значения на месте, но сами утёкшие строки всё ещё
  видны через `git log -p -- docs/deploy.md` в истории репозитория —
  переписывание истории (`git filter-repo`/BFG + force-push) осознанно
  не делалось, это отдельная задача перед публичным ростом.
