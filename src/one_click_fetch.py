import argparse
import csv
import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from csv_to_excel import convert_csv_to_xlsx
from github_pipeline import parse_ozon_links, parse_wb_links


def prompt_lines(title: str) -> List[str]:
    print(f"{title} (пустая строка завершает ввод):")
    lines: List[str] = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if not line.strip():
            break
        lines.append(line.strip())
    return lines


def ensure_cookies_file(raw: str) -> Optional[Path]:
    if not raw:
        return None
    path = Path(raw)
    if path.exists():
        return path
    cookies = []
    for pair in raw.split(";"):
        if "=" not in pair:
            continue
        name, value = pair.split("=", 1)
        cookies.append({"name": name.strip(), "value": value.strip(), "domain": ".ozon.ru", "path": "/"})
    if not cookies:
        return None
    tmp = Path(tempfile.gettempdir()) / "ozon_cookies_inline.json"
    tmp.write_text(json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8")
    return tmp


def to_comma(num: Optional[float]) -> str:
    if num is None:
        return ""
    return str(num).replace(".", ",")


def build_rows(ozon, wb, timestamp: str) -> List[dict]:
    rows = []
    for rec in ozon + wb:
        rows.append(
            {
                "vendor": rec.get("vendor"),
                "product_id": rec.get("product_id"),
                "url": rec.get("url"),
                "name": rec.get("name"),
                "price": rec.get("price"),
                "price_fmt": to_comma(rec.get("price")),
                "fetched_at": timestamp,
            }
        )
    return rows


def write_csv(rows: List[dict], path: Path) -> None:
    if not rows:
        print("Нет данных для записи", file=sys.stderr)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["vendor", "product_id", "url", "name", "price", "price_fmt", "fetched_at"]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"CSV сохранён: {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Однокнопочный сбор цен WB/Ozon -> CSV/Excel")
    parser.add_argument("--out-dir", type=Path, default=Path("output"), help="Куда сохранять результаты")
    parser.add_argument("--ozon-cookies", type=Path, help="Путь к cookies Ozon (JSON).")
    args = parser.parse_args()

    if args.ozon_cookies:
        cookies_path = ensure_cookies_file(str(args.ozon_cookies))
    else:
        cookies_raw = input("Путь к cookies Ozon (json) или строка name=value;name2=value2 (Enter если нет): ").strip()
        cookies_path = ensure_cookies_file(cookies_raw)

    ozon_links = prompt_lines("Вставьте ссылки Ozon")
    wb_links = prompt_lines("Вставьте ссылки Wildberries")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    ozon_records = parse_ozon_links(ozon_links, cookies_path=cookies_path) if ozon_links else []
    wb_records = parse_wb_links(wb_links) if wb_links else []

    rows = build_rows(ozon_records, wb_records, timestamp)
    out_csv = args.out_dir / f"prices_{timestamp}.csv"
    out_xlsx = args.out_dir / f"prices_{timestamp}.xlsx"
    write_csv(rows, out_csv)
    convert_csv_to_xlsx(out_csv, out_xlsx)


if __name__ == "__main__":
    main()
