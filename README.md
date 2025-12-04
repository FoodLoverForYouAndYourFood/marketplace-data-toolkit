# Парсер цен Ozon + Wildberries

Инструмент для продавцов: сверяет карточки Ozon и WB, забирает цены (включая Ozon Карту) и отдаёт готовые CSV и Excel. Есть EXE с окном, прогрессом и логом.

## Что нового
- EXE сам подкачивает Chromium при первом запуске (если не встроен).
- Ссылки можно просто вставить в окно (Ctrl+V); txt-файлы опциональны.
- Логин нужен только для Ozon (WB идёт по API).
- Профиль ищется автоматически (Chrome Default). Если нет — создаётся `output/playwright_profile`.

## Быстрый запуск (EXE, Windows)
Вариант 1. Готовый exe
1) Скачайте `dist/ozon_wb_parser.exe` из релиза/архива.
2) Запустите двойным кликом или командой:  
   `.\ozon_wb_parser.exe`

Вариант 2. Собрать самим
1) Откройте CMD/PowerShell в корне проекта.
2) Выполните:  
   `powershell -ExecutionPolicy Bypass -File build_exe.ps1`
3) Запустите:  
   `.\dist\ozon_wb_parser.exe`

Дальше в окне:
- Вставьте ссылки Ozon и WB (по одной в строке) или выберите txt-файлы.
- Профиль Chrome подставится сам; `chrome.exe` опционален (по умолчанию берётся скачанный Chromium).
- При необходимости нажмите «Открыть окно для логина Ozon», авторизуйтесь и закройте окно.
- Жмите «Старт парсинга» и ждите прогресса. Итог: CSV и XLSX по выбранному пути.

## Запуск из исходников (CLI)
```
pip install -r requirements.txt
python -m playwright install chromium
python src/paired_price_export.py ^
  --oz-links data/links/links_oz.txt ^
  --wb-links data/links/links_wb.txt ^
  --profile-dir "C:\Users\<ВАШ_ПОЛЬЗОВАТЕЛЬ>\AppData\Local\Google\Chrome\User Data\Default" ^
  --browser-path "C:\Program Files\Google\Chrome\Application\chrome.exe" ^
  --skip-html
```

## Что вводить
- Ссылки Ozon и WB должны идти парами по строкам. В окне можно вставить напрямую или выбрать файлы `data/links/links_oz.txt` и `data/links/links_wb.txt`.
- Если ссылки есть и в полях, и в файлах, приоритет у полей. Пустые строки и строки с `#` игнорируются.

## Сборка EXE
```
powershell -ExecutionPolicy Bypass -File build_exe.ps1
```
Скрипт создаёт venv, ставит зависимости, качает Chromium для Playwright и собирает `dist/ozon_wb_parser.exe`. Браузер встраивается, если найден; иначе скачается при первом запуске EXE.

## Связаться
Вопросы и доработки: [t.me/BigFriendlyCat](https://t.me/BigFriendlyCat).
