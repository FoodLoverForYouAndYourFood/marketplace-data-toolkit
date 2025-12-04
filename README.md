# Парсер цен Ozon + Wildberries

Инструмент для продавцов: сверяет карточки Ozon и WB, забирает цены (включая Ozon Карту) и сохраняет CSV и Excel. Есть EXE с окном, прогрессом и логом.

## Что умеет
- Парные ссылки Ozon ↔ WB (по порядку строк).
- Цены Ozon (с картой) + WB, артикул WB, время парсинга.
- Лог и прогресс в окне, готовые CSV+XLSX.

## Запуск EXE (Windows, без готового бинаря)
1) Откройте CMD/PowerShell в папке проекта.
2) Соберите exe:  
   `powershell -ExecutionPolicy Bypass -File build_exe.ps1`
3) Запустите:  
   `.\dist\ozon_wb_parser.exe`
4) В окне:
   - Вставьте ссылки Ozon и WB (по одной в строке) или выберите txt-файлы.
   - Профиль Chrome подставится автоматически; `chrome.exe` опционален (по умолчанию берётся скачанный Chromium).
   - При необходимости нажмите «Открыть окно для логина Ozon», авторизуйтесь и закройте окно.
   - Жмите «Старт парсинга» и дождитесь. Итог: CSV и XLSX по выбранному пути.

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

## Требования
- Windows, Python 3.11+
- Аккаунт Ozon в профиле Chrome/Chromium (для цены с картой).

## Формат ссылок
- Пары по строкам: строка N в Ozon = строка N в WB.
- Пустые строки и строки с `#` игнорируются.
- Приоритет у ссылок, вставленных в поля GUI; если там пусто, берутся файлы `data/links/links_oz.txt` и `data/links/links_wb.txt`.

## Собрать EXE вручную
```
powershell -ExecutionPolicy Bypass -File build_exe.ps1
```
Скрипт создаёт venv, ставит зависимости, качает Chromium для Playwright и собирает `dist/ozon_wb_parser.exe`.

## Контакты
[t.me/BigFriendlyCat](https://t.me/BigFriendlyCat)
