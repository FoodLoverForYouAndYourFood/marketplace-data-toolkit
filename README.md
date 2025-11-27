# Marketplace Price Toolkit

Минимальный набор утилит, который выгружает актуальные цены из карточек Ozon и Wildberries.  
В проекте оставлены только скрипты, входные «примеры» и последние полученные выгрузки.

## Структура

```
data/
  links/                 # примеры списков ссылок (txt, по одной ссылке в строке)
  cookies/
    ozon_cookies.example.json
    wb_cookies.example.json
  html/samples/          # пример сохранённой карточки Ozon (для ориентирования в DOM)
output/
  ozon_prices_*.csv      # отчёты по Ozon (Playwright; с/без Ozon Карты)
  wb_prices_*.csv        # отчёты по WB card API
  paired_prices_*.csv    # общий отчёт Ozon+WB (пари по порядку ссылок)
src/
  ozon_playwright_fetch.py
  github_pipeline.py     # WB + Ozon via API (используется только для WB)
  ...                    # вспомогательные скрипты (build_report.py, html_to_csv.py и т.д.)
```

## Требования

- Python 3.11+  
- `pip install -r requirements.txt`  
- Один раз: `python -m playwright install chromium`

## Подготовка исходных данных

1. **Ссылки.** Отредактируй `data/links/links_oz.txt` и `data/links/links_wb.txt`.  
   Формат: по одной ссылке в строке, `#` — комментарий.
2. **Ozon авторизация.** Есть два сценария:
   - **Через профиль Chrome (рекомендовано).** В профиле уже должен быть выполнен вход на ozon.ru. Выясни путь вида `C:\Users\<ты>\AppData\Local\Google\Chrome\User Data\Default` и передай его в `--profile-dir`.  
   - **Через cookies.** Экспортируй cookies из браузера (например, EditThisCookie) в JSON‑массив вида, как в `data/cookies/ozon_cookies.example.json`, и сохрани в `data/cookies/ozon_cookies.json`.
3. **WB cookies.** Для WB достаточно авторизации по умолчанию, но при необходимости можно подготовить `data/cookies/wb_cookies.json` аналогично примеру.

## Сбор цен Ozon (Playwright)

```powershell
python src/ozon_playwright_fetch.py ^
  --links data/links/links_oz.txt ^
  --profile-dir "C:\Users\<ты>\AppData\Local\Google\Chrome\User Data\Default" ^
  --browser-path "C:\Program Files\Google\Chrome\Application\chrome.exe" ^
  --delay 2 --timeout 120
```

- Скрипт открывает каждую ссылку через Playwright + твой профиль, при необходимости можно добавить `--headless` или `--skip-html` (если не нужны HTML‑снапшоты).  
- Результат сохраняется в `output/ozon_prices_<дата>.csv` с колонками `url`, `product_id`, `name`, `price_with_card`, `price_without_card`, `timestamp`.

## Сбор цен WB (card API)

```powershell
python src/github_pipeline.py ^
  --wb-links data/links/links_wb.txt ^
  --out output/wb_prices_<дата>.csv
```

- Работает через публичный `card.wb.ru` API и не требует Playwright.  
- В CSV пишутся основные поля карточки: `vendor`, `product_id`, `url`, `name`, `price`, `currency`, `rating_value`, `review_count`, `supplier_id/ supplier_name`, `subject_id`.

## Советы

- Если Ozon просит повторную авторизацию, запусти `python -m playwright open --browser=chromium --user-data-dir output/playwright_profile https://www.ozon.ru/`, залогинься и затем используй эту папку в `--profile-dir`.
- Храни свои реальные cookies только локально. В репозитории оставлены `.example` файлы, чтобы было понятно, как выглядит структура JSON.
- `src/paired_price_export.py` объединяет обе выгрузки за один запуск и сразу строит общий CSV `name, ozon_url, wb_url, price_ozon_card, price_wb, wb_article, parsed_at`.  
  Пример команды:
  ```powershell
  python src/paired_price_export.py ^
    --oz-links data/links/links_oz.txt ^
    --wb-links data/links/links_wb.txt ^
    --profile-dir "C:\Users\<ты>s\AppData\Local\Google\Chrome\User Data\Default" ^
    --browser-path "C:\Program Files\Google\Chrome\Application\chrome.exe" ^
    --skip-html
  ```
  Ссылки должны идти в одинаковом порядке (строка 1 в `links_oz` соответствует строке 1 в `links_wb`, и т.д.).
- Новые результаты не перезаписывают старые: каждый запуск создаёт CSV с меткой времени. Просто удаляй лишние файлы из `output/` по необходимости.

Готово — теперь любой пользователь может подставить свои ссылки/куки, запустить два скрипта и сразу получить свежий прайс‑мониторинг.
