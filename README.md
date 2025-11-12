# Marketplace Data Toolkit

Скрипты автоматизируют полный цикл сбора данных о карточках товаров Wildberries и Ozon:

1. **Скачивание HTML** через Playwright с использованием существующего профиля Opera/Chrome.
2. **Парсинг** сохранённых страниц с извлечением структурированной информации.
3. **Запросы к публичным API** (WB) и компоновка данных без HTML.
4. **Формирование итогового Excel-отчёта** в формате, аналогичном `Примеры.xlsx`.

## Структура каталогов

```
data/
  links/           # входные списки ссылок (links_wb.txt, links_oz.txt)
  cookies/         # приватные cookies для Ozon (ozon_cookies.json)
  html/
    ozon/          # HTML, выгруженные Playwright'ом
    samples/       # эталонные страницы для тестов
output/
  products.csv         # выгрузка WB из github_pipeline.py
  ozon_products.csv    # выгрузка из HTML через html_to_csv.py
  products_wb.xlsx     # промежуточный Excel с данными WB
  report.xlsx          # финальный отчёт
src/
  *.py                 # все служебные скрипты
.env.example           # шаблон путей/переменных окружения
```

Перед запуском скопируй `.env.example` в `.env` (или задай переменные любым удобным способом) и укажи свои пути к профилю Opera GX / cookies.

## Требования

- Python 3.11+
- `pip install -r requirements.txt` (минимум: `playwright`, `openpyxl`, `curl_cffi`, `requests`)
- Установленный браузер Opera GX (или Chrome) с рабочей авторизацией на Ozon/WB.
- `python -m playwright install chromium` (для Playwright).

## Скрипты

| Скрипт | Назначение | Основные параметры |
|--------|------------|--------------------|
| `src/ozon_playwright_fetch.py` | Скачивает HTML карточек Ozon, используя указанный профиль Opera/Chrome. Ждёт ручного прохождения антибота перед сохранением каждой страницы. | `--links`, `--out-dir`, `--profile-dir`, `--browser-path`, `--delay`, `--timeout`, `--overwrite` |
| `src/html_to_csv.py` | Парсит сохранённые HTML (Ozon или WB) и формирует CSV через `marketplace_parser.py`. | `--vendor`, `--html-dir`, `--out` |
| `src/marketplace_parser.py` | Общий парсер `application/ld+json` из HTML. Используется как библиотека другими скриптами. | (импортируется) |
| `src/github_pipeline.py` | Получает данные напрямую: WB через `card.wb.ru`, Ozon через `composer-api` (с cookies). Может работать с любым списком ссылок и формирует CSV. | `--wb-links`, `--oz-links`, `--ozon-cookies`, `--out` |
| `src/build_report.py` | Компилирует итоговый Excel (`output/report.xlsx`) с заголовками, формулами маржи и комментариями (рейтинги/отзывы). | `--wb-csv`, `--ozon-csv`, `--out` |

## Типовой сценарий

```bash
# 1. Скачиваем HTML карточек Ozon
python src/ozon_playwright_fetch.py ^
  --links data/links/links_oz.txt ^
  --out-dir data/html/ozon ^
  --profile-dir "C:\Users\FoodLover\AppData\Roaming\Opera Software\Opera GX Stable\Default" ^
  --browser-path "C:\Users\FoodLover\AppData\Local\Programs\Opera GX\opera.exe" ^
  --delay 2 --timeout 120 --overwrite

# 2. Парсим сохранённые HTML в CSV
python src/html_to_csv.py --vendor ozon --html-dir data/html/ozon --out output/ozon_products.csv

# 3. Запрашиваем ассортименты WB и/или Ozon напрямую
python src/github_pipeline.py --wb-links data/links/links_wb.txt --oz-links data/links/links_oz.txt \
  --ozon-cookies data/cookies/ozon_cookies.json --out output/products.csv

# 4. Собираем итоговый Excel-отчет
python src/build_report.py --wb-csv output/products.csv --ozon-csv output/ozon_products.csv --out output/report.xlsx
```

## Примечания

- Для Ozon нужен актуальный набор cookies (`ozon_cookies.json`). Их можно выгрузить из DevTools → Application → Cookies и сохранить в JSON (массив объектов с полями `name`, `value`, `domain`, `path`).
- Playwright требует закрыть Opera GX перед запуском, иначе профиль будет занят.
- WB API постоянно отдаёт `supplierId`, `supplier` и `subjectId`, что используется для заполнения столбцов «ID продавца / Продавец / Предмет».
- В `output/` всегда лежат последняя CSV-выгрузка и Excel-отчёт — их можно коммитить или выгружать в BI.

## Git

Проект уже структурирован для коммита. Добавь `.env` (если нужен) в `.gitignore` и выполняй стандартные шаги:

```bash
git init
git add .
git commit -m "Initial data toolkit"
```

Далее можно привязать удалённый репозиторий и `git push origin main`.
