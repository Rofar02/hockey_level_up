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
openssl rand -hex 32 && echo                    # GLITCHTIP_POSTGRES_PASSWORD
openssl rand -base64 64 | tr -d '\n' && echo    # GLITCHTIP_SECRET_KEY
```

`POSTGRES_PASSWORD`/`RABBITMQ_PASSWORD` specifically as `-hex`, not
`-base64`: `docker-compose.prod.yml` interpolates them straight into
`DATABASE_URL`/`RABBITMQ_URL` (`postgresql+asyncpg://user:PASSWORD@host/db`)
without URL-escaping, so a `/` or `+` from base64 output silently breaks
the URL parser (seen live: RabbitMQ consumer failed to start with a
`port can't be converted to integer` error, no crash, just silently
disabled). Hex output (`0-9a-f`) can never contain a URL-special
character. `JWT_SECRET_KEY` never goes into a URL, base64 is fine there.

VAPID-пару (для push-уведомлений) сгенерировать отдельно и вставить
`VAPID_PUBLIC_KEY`/`VAPID_PRIVATE_KEY` (формат — сырые байты в base64url,
как ждут pywebpush и браузер):

```bash
docker compose -f docker-compose.prod.yml exec backend python -c "
import base64; from py_vapid import Vapid
from cryptography.hazmat.primitives import serialization as s
v = Vapid(); v.generate_keys()
b = lambda x: base64.urlsafe_b64encode(x).rstrip(b'=').decode()
print('VAPID_PRIVATE_KEY=' + b(v.private_key.private_numbers().private_value.to_bytes(32, 'big')))
print('VAPID_PUBLIC_KEY=' + b(v.public_key.public_bytes(s.Encoding.X962, s.PublicFormat.UncompressedPoint)))"
```

С `ENVIRONMENT=production` бэкенд **не стартует**, если `JWT_SECRET_KEY`
короче 32 символов или равен `change-me`, либо `VAPID_PRIVATE_KEY` —
закоммиченный dev-ключ (`app/core/config.py`). Смена `JWT_SECRET_KEY`
разлогинивает всех. Смена VAPID-пары делает старые push-подписки
недействительными: фронт сам переподписывает игрока при следующем открытии
приложения, до этого пушей у него не будет.

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

Миграции (`alembic upgrade head`) применяет одноразовый сервис `migrate`
до старта `backend` и `worker`. Если миграция упала, `docker compose up`
завершится ошибкой, а старые контейнеры продолжат работать. Лог миграций:

```bash
docker compose -f docker-compose.prod.yml logs migrate
```

## 8. Сидирование базы

Пустая прод-БД бесполезна без каталога упражнений/навыков. По порядку
(каждый скрипт идемпотентен — пропускает уже существующие записи, повторный
запуск ничего не сломает):

```bash
docker compose -f docker-compose.prod.yml exec backend python scripts/seed_exercises.py
docker compose -f docker-compose.prod.yml exec backend python scripts/fix_joint_gymnastics_phase.py
docker compose -f docker-compose.prod.yml exec backend python scripts/seed_offseason_catalog_additions.py
docker compose -f docker-compose.prod.yml exec backend python scripts/backfill_warmup_stages.py
docker compose -f docker-compose.prod.yml exec backend python scripts/backfill_coordination_patterns.py
docker compose -f docker-compose.prod.yml exec backend python scripts/backfill_forearms_muscle_group.py
docker compose -f docker-compose.prod.yml exec backend python scripts/seed_skills.py
docker compose -f docker-compose.prod.yml exec backend python scripts/seed_skill_tags.py
docker compose -f docker-compose.prod.yml exec backend python scripts/seed_skill_milestones_skating.py
docker compose -f docker-compose.prod.yml exec backend python scripts/seed_skill_milestones_phase7.py
docker compose -f docker-compose.prod.yml exec backend python scripts/seed_skill_shot_accuracy.py
docker compose -f docker-compose.prod.yml exec backend python scripts/seed_reference_articles.py
```

Порядок в первых командах важен: `fix_joint_gymnastics_phase.py` правит одну
строку по имени (была `phase=main` вместо `warmup` — реальный баг, упражнение
попадало в основную часть тренировки), поэтому идёт сразу после базового
каталога; `seed_offseason_catalog_additions.py` добавляет новые упражнения
(тоже должен идти после базового каталога); `backfill_warmup_stages.py`
правит уже существующие по имени строки, так что запускается последним. Все
скрипты идемпотентны (пропускают уже существующее) — безопасно
перезапускать при повторном деплое, если каталог обновился.

`retag_equipment_mistags.py` (упомянутый в более старых версиях этого файла)
удалён 2026-08-20 вместе с самим полем `equipment_type` (Этап 2.2 —
инвентарь теперь список конкретных предметов, `ExerciseEquipmentItem`, а не
одна тройка gym/home/bodyweight) — его правки уже отражены в бэкфилле
миграции `72b50a73e77b`, повторно применять нечего.

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

Что попадает в бэкап: дамп Postgres (`db-ДАТА.sql.gz`) и архив загрузок —
аватары, картинки статей, логотипы команд, скриншоты из обратной связи
(`uploads-ДАТА.tar.gz`). На сервере хранятся 14 дней.

### 10.1. Копия вне сервера

Если сервер пропадёт целиком, локальные бэкапы пропадут вместе с ним. Поэтому
`backup.sh` после локальных архивов шифрует их (gpg, AES256 — в дампе почты и
хэши паролей) и загружает через rclone в S3-совместимое хранилище, где они
живут 30 дней. Ролики упражнений (`/srv/hlu-media/exercise-videos`)
синхронизируются туда же без шифрования (это публичный контент).

1. Поставить rclone и gpg: `apt install -y rclone gnupg`.
2. Создать бакет (например, Yandex Object Storage — данные остаются в РФ)
   и сервисный ключ доступа только к нему.
3. В `.env` заполнить `BACKUP_PASSPHRASE`, `BACKUP_REMOTE` и
   `RCLONE_CONFIG_OFFSITE_*` (образец в `.env.prod.example`).
   **Пароль `BACKUP_PASSPHRASE` сохранить вне сервера** (менеджер паролей) —
   без него бэкап не расшифровать.
4. Запустить `deploy/backup.sh` руками, убедиться, что в бакете появились
   `daily/db-ДАТА.sql.gz.gpg` и `daily/uploads-ДАТА.tar.gz.gpg`.
5. Проверить, что бэкап реально восстанавливается:

   ```bash
   deploy/restore_check.sh                                    # последний локальный дамп
   rclone copy offsite:icelevel-backups/daily/db-ДАТА.sql.gz.gpg /tmp/
   deploy/restore_check.sh /tmp/db-ДАТА.sql.gz.gpg            # копия из хранилища
   ```

   Скрипт поднимает временный Postgres, заливает дамп, считает игроков и
   удаляет контейнер — боевую базу не трогает. Повторять раз в месяц.

### 10.2. Восстановление прода из бэкапа

1. Остановить всё, что пишет в базу:
   `docker compose -f docker-compose.prod.yml stop backend worker nginx`.
2. Если дамп из хранилища — скачать и расшифровать:

   ```bash
   rclone copy offsite:icelevel-backups/daily/db-ДАТА.sql.gz.gpg /tmp/
   gpg --decrypt --output /tmp/db.sql.gz /tmp/db-ДАТА.sql.gz.gpg   # спросит BACKUP_PASSPHRASE
   ```

3. Пересоздать базу и залить дамп (`source .env` даёт `POSTGRES_USER`/`POSTGRES_DB`):

   ```bash
   source .env
   docker compose -f docker-compose.prod.yml exec -T postgres      psql -U "$POSTGRES_USER" -d postgres -c "DROP DATABASE \"$POSTGRES_DB\"" -c "CREATE DATABASE \"$POSTGRES_DB\""
   gunzip -c /tmp/db.sql.gz | docker compose -f docker-compose.prod.yml exec -T postgres      psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"
   ```

4. Загрузки — распаковать архив обратно в тома:

   ```bash
   docker run --rm -v icelevel_avatars_data:/avatars -v icelevel_reference_articles_data:/reference-articles      -v icelevel_team_logos_data:/team-logos -v icelevel_feedback_data:/feedback      -v /tmp:/backup alpine tar xzf /backup/uploads-ДАТА.tar.gz -C /
   ```

5. Поднять всё обратно: `docker compose -f docker-compose.prod.yml up -d`
   (сервис `migrate` догонит миграции, если код новее дампа), затем смок-тест
   из раздела 12.

## 11. Обновление сервера (обычный рабочий цикл)

Локально: разработка в этом репозитории, коммит, `git push`. На сервере:

```bash
cd /opt/icelevel
./deploy/deploy.sh
```

Делает `git pull --ff-only` + `docker compose up -d --build` + подчищает
старые образы + сразу показывает хвост логов backend (чтобы упавшая
миграция была видна сразу, а не через час).

### 11.1. Видео упражнений (ролики и обложки)

Ролики (`*.mp4`, 480p без звука) и обложки (`*.jpg`) лежат **не в
репозитории** и **не в томе Docker**, а в обычной папке на сервере
`/srv/hlu-media/exercise-videos/`. Её читает только edge-nginx
(`docker-compose.prod.yml`, bind mount, read-only) и отдаёт по адресу
`/media/exercise-videos/<id>.mp4` напрямую, без Python-бэкенда.

Первый раз:

1. На сервере: `mkdir -p /srv/hlu-media/exercise-videos`.
2. С локальной машины залить файлы (около 250 МБ):
   `rsync -avz --progress static/exercise-videos/ root@<сервер>:/srv/hlu-media/exercise-videos/`
   (с Windows — `scp -r` или rsync из WSL). Оригиналы из
   `exercise-videos-originals/` на сервер **не нужны**.
3. Обновить `deploy/nginx/active.conf` из `deploy/nginx/app.conf` (в нём
   новый блок `location /media/exercise-videos/`) и **пересоздать**
   nginx: `docker compose -f docker-compose.prod.yml up -d nginx`
   (новый bind mount подхватывается только при пересоздании, одного
   `reload` мало).
4. Пересобрать фронтенд — адрес медиа вшивается в сборку
   (`VITE_MEDIA_BASE_URL=/media/exercise-videos`):
   `docker compose -f docker-compose.prod.yml up -d --build frontend`.
5. Проверка: `curl -I https://icelevel.ru/media/exercise-videos/<id>.mp4`
   даёт `200`, `Cache-Control: public, max-age=2592000, immutable`; с
   заголовком `Range: bytes=0-999` — `206`.
6. Привязки в БД (`video_source_type='file'`, `video_source_id=<имя файла
   без .mp4>`) на прод переносятся отдельным скриптом, **не** полным
   `import_master_catalog.py`.

Замена ролика: класть под **новым** именем и менять `video_source_id`
(браузеры кэшируют файл на 30 дней, под старым именем обновление не
доедет).

Переезд на отдельный/больший диск: подключить диск, смонтировать в
`/srv/hlu-media` (или скопировать `rsync -a` и перемонтировать), nginx
перезапустить. Адреса в приложении не меняются.

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
  22/80/443, не 5432/5672/15672/8080 (последний — GlitchTip, раздел 13,
  `127.0.0.1:8080` в docker-compose.prod.yml не публикуется наружу).

## 13. GlitchTip — мониторинг ошибок (бэкенд)

Self-hosted, Sentry-протокол-совместимый (Sentry сам заблокирован для
пользователей из России с сентября 2024 — не только оплата, сам доступ).
Живёт полностью во внутренней docker-сети, наружу не торчит ни один
порт — только бэкенд шлёт туда ошибки, смотреть их можно через
SSH-туннель. Браузерные ошибки фронтенда сюда пока не подключены
(отдельная задача — публичный поддомен + свой TLS).

Секреты (`GLITCHTIP_POSTGRES_PASSWORD`, `GLITCHTIP_SECRET_KEY`) уже
сгенерированы в шаге 4 — убедиться, что они в `.env`. `GLITCHTIP_DSN`
пока оставить пустым (это финальный шаг ниже).

Поднять сервисы (входят в общий `docker compose up -d --build` из шага 6,
если `.env` уже заполнен на момент первого деплоя — иначе просто:

```bash
docker compose -f docker-compose.prod.yml up -d \
  glitchtip_postgres glitchtip_redis glitchtip_migrate glitchtip_web glitchtip_worker
```

Создать единственный админ-логин (не через веб-регистрацию —
`ENABLE_USER_REGISTRATION` выключен):

```bash
docker compose -f docker-compose.prod.yml exec glitchtip_web ./manage.py createsuperuser
```

С локальной машины — туннель и вход:

```bash
ssh -L 8080:localhost:8080 root@<IP сервера>
```

Открыть `http://localhost:8080`, войти созданным логином, создать
организацию и проект (`platform: Python` — под FastAPI-бэкенд). GlitchTip
покажет DSN вида `http://<public_key>@localhost:8080/<project_id>` —
взять из него только `<public_key>` и `<project_id>`, собрать серверный
DSN вручную (localhost в показанном DSN — это адрес *с точки зрения
браузера через туннель*, бэкенду внутри compose-сети нужен адрес по
имени сервиса):

```
GLITCHTIP_DSN=http://<public_key>@glitchtip_web:8080/<project_id>
```

Вписать в `.env` на сервере, перезапустить бэкенд:

```bash
docker compose -f docker-compose.prod.yml up -d backend
```

Проверить тестовым событием (не дожидаясь настоящей ошибки):

```bash
docker compose -f docker-compose.prod.yml exec backend python -c "
import sentry_sdk
from app.core.config import get_settings
sentry_sdk.init(dsn=get_settings().glitchtip_dsn)
sentry_sdk.capture_message('GlitchTip test event from deploy runbook')
sentry_sdk.flush()
"
```

Событие должно появиться в `http://localhost:8080` (через туннель) в
том же проекте в течение нескольких секунд.

### 13.1. Письма на почту при новых ошибках

`EMAIL_URL` в `x-glitchtip-env` (docker-compose.prod.yml) уже настроен
на SMTP-релей Resend — тот же аккаунт, что и `RESEND_API_KEY` для
писем самого приложения, отдельного провайдера заводить не нужно.
`icelevel.ru` — подтверждённый домен на этом аккаунте, поэтому
`DEFAULT_FROM_EMAIL: glitchtip@icelevel.ru` доставляется без проблем.

GlitchTip сам не присылает алерты по умолчанию — нужно один раз
включить это в UI (через тот же SSH-туннель):

1. Открыть проект → **Settings → Alerts** (или **Notifications** —
   название зависит от версии).
2. Добавить правило: *When an issue is first seen* (или *A new issue is
   created*) → **Send email** → выбрать себя как получателя.
3. В **Settings → Notifications** личного профиля убедиться, что email
   вообще не отключён глобально (по умолчанию включён).

Проверить: `sentry_sdk.capture_message(...)` тем же способом, что и
тестовое событие выше — письмо должно дойти в течение минуты.

## 14. Аварийный service worker (если телефоны застряли на сломанной сборке)

Когда нужен: после релиза у игроков белый экран или приложение не
открывается, а исправленная сборка уже на сервере, но телефоны её не
берут (старый service worker держит кэш и ждёт «безопасного момента»).

Каждая сборка кладёт рядом с `/sw.js` файл `/sw-safe.js`
(`frontend/src/sw-safe.ts`). Он при установке сразу перехватывает
управление, **удаляет все кэши**, не имеет обработчика `fetch` (приложение
грузится из сети, как обычный сайт) и перезагружает открытые вкладки.
Push-уведомления в нём сохранены.

Выкатить (на сервере, без пересборки):

```bash
cd /opt/icelevel
docker compose -f docker-compose.prod.yml exec frontend   sh -c 'cp /usr/share/nginx/html/sw-safe.js /usr/share/nginx/html/sw.js'
curl -s https://icelevel.ru/sw.js | head -3   # должно начинаться с комментария про emergency
```

Телефон подхватит его при следующем открытии приложения (браузер
проверяет `/sw.js` на каждой навигации, `Cache-Control: no-cache`).
Обычно сразу, в крайнем случае — после того как игрок закроет и снова
откроет приложение.

**Не использовать** `registration.unregister()` и «удалить service worker»
на сервере: вместе с ним пропадает push-подписка, и игроки перестанут
получать уведомления, не узнав об этом.

Вернуть обычный режим: следующий обычный деплой (`./deploy/deploy.sh`)
пересобирает контейнер `frontend`, в нём снова настоящий `sw.js` —
телефоны обновятся сами, офлайн-режим вернётся. Если деплоя не будет,
пересобрать только фронтенд:
`docker compose -f docker-compose.prod.yml up -d --build frontend`.

Проверка локально: `e2e/sw-offline.spec.ts`, тест «the emergency worker».

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
