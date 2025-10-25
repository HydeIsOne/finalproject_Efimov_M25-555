# ValutaTrade Hub

Платформа для отслеживания и симуляции торговли валютами (учебный финальный проект). Проект оформлен как Python-пакет и предоставляет консольный интерфейс (CLI).

## Стек и инструменты
- Python 3.13
- Poetry — управление зависимостями и сборкой
- Ruff — линтер и форматтер (PEP8)
- PrettyTable — форматированный вывод таблиц
- Requests — HTTP‑клиент для работы с внешними API
- python-dotenv — загрузка переменных окружения из .env


## Быстрый старт
> Требуется установленный Poetry. На Windows удобно через pipx: `pipx install poetry`.

- Установка зависимостей:
```
make install
```
- Запуск CLI (скелет):
```
make project
```
- Сборка пакета:
```
make build
```
- Проверка линтером:
```
make lint
```

Примечание для Windows: Makefile лучше запускать из Git Bash или установить совместимую реализацию make. Если make недоступен, используйте альтернативу: `poetry run project` (аналог `make project`).

## Доступные команды CLI
- register — регистрация пользователя
- login — вход пользователя (создает локальную сессию)
- show-portfolio — показать портфель в базовой валюте (по умолчанию USD)
- buy — купить валюту (списывает USD)
- sell — продать валюту (зачисляет USD)
- deposit — пополнить кошелёк (по умолчанию USD)
- withdraw — снять средства с кошелька (по умолчанию USD)
- get-rate — получить курс пары (с локальным кешем)
- list-currencies — показать список поддерживаемых валют
- update-rates — обновить курсы из внешних API (Parser Service)
	- флаги: `--source exchangerate|coingecko`, `--strict` (жесткая замена снимка без слияний), `--all-fiat` (все фиатные валюты, иначе по умолчанию только EUR/GBP/RUB), `--no-history` (не писать в `exchange_rates.json` для этого запуска)
- schedule [--interval 300] [--source exchangerate|coingecko] [--strict] [--all-fiat] [--no-history] — периодическое обновление (идет в цикле до Ctrl+C)
- show-rates — показать актуальные курсы из локального кэша (опции: `--currency`, `--top`, `--base` для пересчета в базовую валюту)
- clear-history — очистить `data/exchange_rates.json`

Пример запуска (через make):
```
make project -- register --username alice --password 1234
make project -- login --username alice --password 1234
make project -- deposit --amount 1000
make project -- show-portfolio
make project -- buy --currency EUR --amount 10
make project -- get-rate --from EUR --to USD
make project -- list-currencies
```

## REPL-режим
Если запустить CLI без аргументов, откроется REPL. Короткая справка по командам доступна через `help`.

Примеры:
```
login --username alice --password 1234
update-rates --strict --no-history
show-rates --base EUR --currency BTC
schedule --interval 600 --strict
```

## Исключения и сообщения
Пользователь видит дружелюбные сообщения об ошибках:
- InsufficientFundsError → «Недостаточно средств: доступно X CODE, требуется Y CODE»
- CurrencyNotFoundError → «Неизвестная валюта 'XXX'» + подсказка проверить код
- ApiRequestError → «Ошибка при обращении к внешнему API: причина» + подсказка повторить позже

## Логи
Логирование настраивается в `valutatrade_hub/logging_config.py` (вращающиеся файлы + вывод в консоль). Декоратор `@log_action` проставлен на операции BUY/SELL, а также REGISTER/LOGIN. В лог попадают: timestamp, действие, user_id/username (когда доступны), валюта/сумма/курс (когда применимо), результат (OK/ERROR).

## TTL кэша курсов
Курсы сохраняются в `data/rates.json` с TTL (по умолчанию 300 сек), задается через `[tool.valutatrade]` в `pyproject.toml` (ключ `rates_ttl_seconds`). При истечении TTL автоматически триггерится обновление через Parser Service.

Дополнительно реализовано «ежедневное автообновление при запуске»: если `last_refresh` в `data/rates.json` относится к прошлому дню, при старте CLI выполняется одноразовое обновление (best-effort). Поведение можно отключить переменной окружения `PARSER_AUTO_UPDATE_ON_START=0`.

Планировщик (ручной запуск):
- Команда `schedule` запускает обновление в цикле с заданным интервалом.
- Пример (PowerShell):
```
poetry run project schedule --interval 600 --strict --no-history
```
Нажмите Ctrl+C для остановки. Флаги аналогичны `update-rates`.

## Иерархия валют
В `valutatrade_hub/core/currencies.py` реализована иерархия валют с реестром поддерживаемых кодов (USD, EUR, RUB, BTC, ETH). Команда `list-currencies` выводит список поддерживаемых валют.

## Статус
Реализованы модели (User/Wallet/Portfolio), use cases с JSON-персистентностью, кастомные исключения, логирование и декораторы, иерархия валют, REPL и расширенный CLI (включая list-currencies). Подключён Parser Service с внешними провайдерами (ExchangeRate-API для фиата и CoinGecko для крипто), поддерживаются история измерений и снимок кэша в `data/`.

## Parser Service: обновление курсов, история и .env

В проекте есть отдельный сервис парсинга `valutatrade_hub/parser_service`:
- История (журнал измерений): `data/exchange_rates.json`
	- Каждая запись содержит уникальный `id` вида `FROM_TO_YYYY-MM-DDTHH:MM:SSZ`, `rate`, `timestamp` (UTC, ISO, Z), `source`, `meta{raw_id, request_ms, status_code, etag}`
	- Запись выполняется атомарно; дубликаты по `id` не добавляются
- Снимок (быстрый кэш): `data/rates.json`
	- Формат: `{ "pairs": { "EUR_USD": { "rate", "updated_at", "source" } }, "last_refresh": "..." }`
	- Сохраняются обе стороны пары (EUR_USD и USD_EUR); при конфликте побеждает более свежий `updated_at`

Команды CLI:
- `update-rates [--source exchangerate|coingecko] [--strict] [--all-fiat] [--no-history]` — одноразовое обновление
- `show-rates [--currency BTC] [--top 2] [--base USD]` — просмотр кэша
- `schedule [--interval 300] [--source exchangerate|coingecko] [--strict] [--all-fiat] [--no-history]` — периодическое обновление в цикле
- `clear-history` — очистка истории измерений (`data/exchange_rates.json`)

Переменные окружения и .env:
- Поддерживается загрузка `.env` (python-dotenv), приоритет: реальные переменные окружения > значения из .env
- Фиат (ExchangeRate-API):
	- Вариант A (полный URL): `EXCHANGERATE_API_URL=https://v6.exchangerate-api.com/v6/<KEY>/latest/USD`
	- Вариант B (ключ отдельно): `EXCHANGERATE_API_KEY=<KEY>`, опционально `EXCHANGERATE_BASE=USD`
- Крипто (CoinGecko): ключ не требуется для simple/price
	- Вариант A (полный URL): `COINGECKO_FULL_URL=https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,solana&vs_currencies=usd`
	- Вариант B (базовый URL): `COINGECKO_URL=https://api.coingecko.com/api/v3/simple/price` — ids берутся из CRYPTO_ID_MAP
- Таймаут HTTP: `PARSER_HTTP_TIMEOUT=10`

Режимы Parser Service и область валют:
- По умолчанию фиат ограничен до трех валют (EUR, GBP, RUB); крипто — BTC, ETH, SOL
- Для разового расширения до всех фиатных — используйте флаг `--all-fiat`
- Поведение снимка (rates.json):
	- обычный режим — «слияние по свежести» (более свежие значения перекрывают старые)
	- строгий режим — полная замена снимка текущим набором пар. Можно включить флагом `--strict` или переменной окружения `PARSER_SNAPSHOT_STRICT=1`
- История измерений (exchange_rates.json) может быть временно отключена флагом `--no-history` или переменной `PARSER_HISTORY_DISABLED=1`

Примеры для PowerShell (Windows):
```
# Разово для текущей сессии
$env:EXCHANGERATE_API_URL = "https://v6.exchangerate-api.com/v6/<KEY>/latest/USD"
# или
$env:EXCHANGERATE_API_KEY = "<KEY>"

# Запуск обновления
make project -- update-rates

# Постоянная установка ключа (нужно перезапустить терминал)
setx EXCHANGERATE_API_KEY "<KEY>"
```

Файл `.env` хранится локально, он уже в `.gitignore`. Пример — `.env.example`.

## Сессия
Данные активной сессии (после login) хранятся во временной папке системы и не попадают в репозиторий. Формат имени файла: `vth_session_<id>.json`, где `<id>` уникален для проекта. В текущей версии выход из сессии выполняется автоматически при следующем входе другим пользователем.

***
Учебный проект: «Платформа для отслеживания и симуляции торговли валютами».