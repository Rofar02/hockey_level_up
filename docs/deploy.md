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

Зайти на сервер по SSH как `root`, скопировать `deploy/server-setup.sh`
(например, через `scp`, либо просто открыть файл на GitHub и вставить
содержимое через `nano`), прочитать (он открывает файрвол и меняет настройки
SSH — не запускать вслепую), затем:

```bash
chmod +x server-setup.sh
./server-setup.sh
```

Скрипт: ставит Docker + Compose plugin, создаёт пользователя `icelevel`
(без пароля, только по ключу, добавлен в группу `docker`), включает UFW
(разрешены только 22/80/443), fail2ban, unattended-upgrades, готовит sshd к
отключению входа по паролю/root — но **не перезапускает sshd
автоматически**. В конце скрипт сам это напомнит:

1. В **новом** терминале убедиться, что вход по SSH как `icelevel` со своим
   ключом работает.
2. Только после этого: `systemctl restart sshd`.

Если на сервере ≤2GB RAM — скрипт сам добавит 2GB swap (сборка фронтенда
`npm run build` иначе может упасть по памяти).

## 2. DNS

У регистратора/в панели Timeweb добавить:

```
A    icelevel.ru       → <IP сервера>
A    www.icelevel.ru   → <IP сервера>
```

Подождать распространения, проверить: `dig icelevel.ru +short`.

## 3. Клонирование репозитория

Под пользователем `icelevel`:

```bash
sudo mkdir -p /opt/icelevel && sudo chown icelevel:icelevel /opt/icelevel
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

Готовые сгенерированные значения (вставить как есть, менять не нужно —
сгенерированы отдельно от сервера, специально под этот деплой):

```
JWT_SECRET_KEY=***REMOVED-JWT-SECRET***
POSTGRES_PASSWORD=***REMOVED-POSTGRES-PASSWORD***
RABBITMQ_PASSWORD=***REMOVED-RABBITMQ-PASSWORD***
VAPID_PRIVATE_KEY=***REMOVED-VAPID-PRIVATE-KEY***
VAPID_PUBLIC_KEY=***REMOVED-VAPID-PUBLIC-KEY***
```

`RESEND_API_KEY` — вставить свой реальный ключ Resend (тот же, что
используется локально, либо новый — но см. шаг 9 про верификацию домена,
без неё письма реальным пользователям не дойдут). `POSTGRES_USER`,
`RABBITMQ_USER` можно оставить как в примере (`icelevel`).

Если храните эти значения где-то отдельно (менеджер паролей) — сохраните
их сейчас, `docs/deploy.md` в репозитории эти конкретные значения хранить не
должен (это одноразовая передача, дальше — только в `.env` на сервере и, по
желанию, в вашем секретном хранилище).

## 5. Сертификат — bootstrap-фаза (курица и яйцо)

`deploy/nginx/app.conf` ссылается на файлы сертификата, которых ещё нет —
nginx с ним не запустится. Сначала поднимаем HTTP-only конфиг:

```bash
cp deploy/nginx/bootstrap.conf deploy/nginx/active.conf
docker compose -f docker-compose.prod.yml up -d nginx
```

Проверить, что `http://icelevel.ru` отвечает (текст про bootstrap). Затем
выпустить сертификат:

```bash
docker compose -f docker-compose.prod.yml run --rm certbot \
  certonly --webroot -w /var/www/certbot \
  -d icelevel.ru -d www.icelevel.ru \
  --email lexa95k@gmail.com --agree-tos --no-eff-email
```

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
docker compose -f docker-compose.prod.yml exec backend python scripts/seed_skills.py
docker compose -f docker-compose.prod.yml exec backend python scripts/seed_skill_tags.py
docker compose -f docker-compose.prod.yml exec backend python scripts/seed_skill_milestones_skating.py
docker compose -f docker-compose.prod.yml exec backend python scripts/seed_skill_milestones_phase7.py
docker compose -f docker-compose.prod.yml exec backend python scripts/seed_skill_shot_accuracy.py
docker compose -f docker-compose.prod.yml exec backend python scripts/seed_reference_articles.py
```

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
sudo crontab -e
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
