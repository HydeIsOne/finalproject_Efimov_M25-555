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

## Статус
Сейчас создана структура проекта и базовые файлы конфигурации. Реализация функциональности (модели, use cases, CLI-логика, парсер сервис) будет добавлена на следующих этапах.

***
Учебный проект: «Платформа для отслеживания и симуляции торговли валютами».