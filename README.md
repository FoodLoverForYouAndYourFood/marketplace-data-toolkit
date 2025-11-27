# Инструкция по запуску (Ozon + WB)

Простой инструмент: берёте два списка ссылок (Ozon и WB) и получаете готовый отчёт в CSV и XLSX.

## Что нужно
1) Windows и установленный Python 3.11+
2) Зависимости:
   - pip install -r requirements.txt
   - python -m playwright install chromium
3) Google Chrome, где вы уже залогинены в Ozon (чтобы видеть цены с Ozon Картой). Закройте Chrome перед запуском.

## Куда вставлять ссылки
- data/links/links_oz.txt — ссылки Ozon, по одной в строке.
- data/links/links_wb.txt — ссылки WB, по одной в строке.
Строки должны совпадать по порядку: первая строка Ozon = первая строка WB и т.д. Можно ставить # для комментариев.

## Как запустить
Откройте PowerShell в папке проекта:

cd C:\Users\FoodLover\Documents\PetProjects\Parser_exe

Выполните команду (при необходимости поменяйте пути к профилю и браузеру):

python src/paired_price_export.py ^
  --oz-links data/links/links_oz.txt ^
  --wb-links data/links/links_wb.txt ^
  --profile-dir "C:\Users\FoodLover\AppData\Local\Google\Chrome\User Data\Default" ^
  --browser-path "C:\Program Files\Google\Chrome\Application\chrome.exe" ^
  --skip-html

Важно:
- --profile-dir — папка профиля Chrome, где есть вход в Ozon.
- --browser-path — путь до chrome.exe.
- --skip-html — не сохранять HTML (можно убрать, если нужны снапшоты).

## Результат
В output/ появятся файлы paired_prices_<дата>.csv и paired_prices_<дата>.xlsx.
Колонки в отчёте:
- name — название
- ozon_url, wb_url — исходные ссылки
- price_ozon_card — цена с Ozon Картой
- price_wb — цена WB
- wb_article — артикул WB
- parsed_at — время парсинга

## Если не логинится Ozon
1) Выполните: python -m playwright open --browser=chromium --user-data-dir output/playwright_profile https://www.ozon.ru/
2) Залогиньтесь вручную, закройте окно.
3) Запустите основную команду, указав --profile-dir output/playwright_profile.

## Минимальный набор файлов
- src/paired_price_export.py, src/ozon_playwright_fetch.py, src/github_pipeline.py, src/marketplace_parser.py
- data/links/links_oz.txt, data/links/links_wb.txt
- data/cookies/*.example.json (шаблоны, если захотите использовать cookies)
- output/ — сюда пишется результат.