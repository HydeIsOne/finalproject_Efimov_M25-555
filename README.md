# ValutaTrade Hub

Платформа для отслеживания и симуляции торговли валютами (учебный финальный проект). Проект оформлен как Python-пакет и предоставляет консольный интерфейс (CLI).

## Стек и инструменты
- Python 3.13
- Poetry — управление зависимостями и сборкой
- Ruff — линтер и форматтер (PEP8)
- PrettyTable — форматированный вывод таблиц

## Структура проекта
```
finalproject_Efimov_M25-555/
├── data/
│   ├── users.json
│   ├── portfolios.json
│   └── rates.json
├── valutatrade_hub/
│   ├── __init__.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── models.py
│   │   ├── utils.py
│   │   └── usecases.py
│   └── cli/
│       ├── __init__.py
│       └── interface.py
├── main.py
├── Makefile
├── poetry.lock (генерируется Poetry)
├── pyproject.toml
├── README.md
└── .gitignore
```

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

Примечание для Windows: Makefile лучше запускать из Git Bash или установить совместимую реализацию make. Либо команды Poetry можно выполнять напрямую в PowerShell.

## Доступные команды CLI
- register — регистрация пользователя
- login — вход пользователя (создает локальную сессию)
- show-portfolio — показать портфель в базовой валюте (USD)
- buy — купить валюту (списывает USD)
- sell — продать валюту (зачисляет USD)
- get-rate — получить курс пары (с локальным кешем)

Пример запуска (через make):
```
make project -- register --username alice --password 1234
make project -- login --username alice --password 1234
make project -- show-portfolio
make project -- buy --currency EUR --amount 10
make project -- get-rate --from EUR --to USD
```

## Статус
Реализованы модели (User/Wallet/Portfolio), use cases с JSON-персистентностью и CLI-команды, перечисленные выше. Линтер/форматтер настроены. Сервис парсинга курсов вынесен в отдельную точку расширения (заглушка), сейчас используются локальные дефолтные курсы и кеш в файле `data/rates.json`.

## Сессия
Данные активной сессии (после login) хранятся во временной папке системы и не попадают в репозиторий. Формат имени файла: `vth_session_<id>.json`, где `<id>` уникален для проекта. В текущей версии выход из сессии выполняется автоматически при следующем входе другим пользователем.

***
Учебный проект: «Платформа для отслеживания и симуляции торговли валютами».