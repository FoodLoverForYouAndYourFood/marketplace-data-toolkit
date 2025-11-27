import argparse
import csv
import os
import tkinter as tk
from tkinter import filedialog, messagebox
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Sequence

from csv_to_excel import convert_csv_to_xlsx
from github_pipeline import parse_wb_links, read_links as read_wb_links
from ozon_playwright_fetch import PriceRecord, download_pages, read_links as read_oz_links

def _zip_pairs(
    oz_records: Sequence[PriceRecord],
    wb_records: Sequence[dict],
    oz_links: Sequence[str],
    wb_links: Sequence[str],
) -> List[dict]:
    limit = min(len(oz_records), len(wb_records), len(oz_links), len(wb_links))
    rows: List[dict] = []
    for idx in range(limit):
        oz = oz_records[idx]
        wb = wb_records[idx]
        wb_price = wb.get("price")
        rows.append(
            {
                "name": oz.name or wb.get("name") or "",
                "ozon_url": oz_links[idx],
                "wb_url": wb_links[idx],
                "price_ozon_card": oz.price_with_card or "",
                "price_wb": str(wb_price) if wb_price is not None else "",
                "wb_article": wb.get("product_id") or "",
                "parsed_at": oz.timestamp,
            }
        )
    return rows

def _write_rows(rows: List[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "name",
                "ozon_url",
                "wb_url",
                "price_ozon_card",
                "price_wb",
                "wb_article",
                "parsed_at",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)
    convert_csv_to_xlsx(path, path.with_suffix(".xlsx"))


def build_cli() -> argparse.ArgumentParser:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    default_out = Path("output") / f"paired_prices_{timestamp}.csv"
    parser = argparse.ArgumentParser(description="Fetch paired Ozon+WB prices and build combined CSV.")
    parser.add_argument("--oz-links", type=Path, help="File with Ozon links.")
    parser.add_argument("--wb-links", type=Path, help="File with WB links.")
    parser.add_argument("--profile-dir", type=Path, help="Browser profile directory (Chromium/Chrome).")
    parser.add_argument("--browser-path", type=Path, help="Browser executable (chrome.exe).")
    parser.add_argument("--oz-html-dir", type=Path, default=Path("data/html/ozon"), help="Where to store Ozon HTML.")
    parser.add_argument("--out", type=Path, default=default_out, help=f"Destination CSV (default: {default_out}).")
    parser.add_argument("--headless", action="store_true", help="Run browser headless.")
    parser.add_argument("--delay", type=float, default=1.5, help="Delay between pages (seconds).")
    parser.add_argument("--timeout", type=int, default=90, help="Navigation timeout (seconds).")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite HTML snapshots if saved.")
    parser.add_argument("--manual-confirm", action="store_true", help="Pause after each navigation until Enter is pressed.")
    parser.add_argument("--skip-html", action="store_true", help="Do not write HTML snapshots to disk.")
    parser.add_argument("--gui", action="store_true", help="Show GUI prompts for paths instead of CLI args.")
    return parser

def guess_chrome_browser() -> Optional[Path]:
    for path in [
        Path("C:/Program Files/Google/Chrome/Application/chrome.exe"),
        Path("C:/Program Files (x86)/Google/Chrome/Application/chrome.exe"),
    ]:
        if path.exists():
            return path
    return None

def guess_chrome_profile() -> Optional[Path]:
    user = os.environ.get("USERPROFILE")
    if not user:
        return None
    path = Path(user) / "AppData/Local/Google/Chrome/User Data/Default"
    return path if path.exists() else None

def run_gui() -> argparse.Namespace:
    root = tk.Tk()
    root.withdraw()
    messagebox.showinfo("Парсинг", "Если Chrome найден автоматически, шаги выбора пропустятся.")

    default_oz = Path("data/links/links_oz.txt")
    default_wb = Path("data/links/links_wb.txt")
    oz_links = str(default_oz) if default_oz.exists() else ""
    wb_links = str(default_wb) if default_wb.exists() else ""
    profile_dir = guess_chrome_profile()
    browser_path = guess_chrome_browser()

    if not oz_links:
        oz_links = filedialog.askopenfilename(title="Файл ссылок Ozon", initialdir="data/links", filetypes=[("Text", "*.txt"), ("All", "*.*")])
    if not wb_links:
        wb_links = filedialog.askopenfilename(title="Файл ссылок WB", initialdir="data/links", filetypes=[("Text", "*.txt"), ("All", "*.*")])
    if not profile_dir:
        pd = filedialog.askdirectory(title="Папка профиля браузера")
        profile_dir = Path(pd) if pd else None
    if not browser_path:
        bp = filedialog.askopenfilename(title="Исполняемый файл браузера (chrome.exe)", initialdir="C:/Program Files/Google/Chrome/Application")
        browser_path = Path(bp) if bp else None
    out = filedialog.asksaveasfilename(
        title="Куда сохранить CSV",
        defaultextension=".csv",
        initialfile=f"paired_prices_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        initialdir="output",
    )

    if not all([oz_links, wb_links, profile_dir, browser_path, out]):
        raise SystemExit("Выбор отменён")

    return argparse.Namespace(
        oz_links=Path(oz_links),
        wb_links=Path(wb_links),
        profile_dir=Path(profile_dir), # type: ignore
        browser_path=Path(browser_path), # type: ignore
        oz_html_dir=Path("data/html/ozon"),
        out=Path(out),
        headless=False,
        delay=1.5,
        timeout=90,
        overwrite=True,
        manual_confirm=False,
        skip_html=False,
    )

def main() -> None:
    parser = build_cli()
    args = parser.parse_args()

    if args.gui:
        args = run_gui()
    else:
        if not args.oz_links or not args.wb_links or not args.profile_dir:
            parser.error("Arguments --oz-links, --wb-links, --profile-dir are required unless --gui is used.")

    oz_links = read_oz_links(args.oz_links)
    wb_links = read_wb_links(args.wb_links)
    if not oz_links or not wb_links:
        raise SystemExit("Both link files must contain at least one URL.")
    if len(oz_links) != len(wb_links):
        print(
            f"[WARN] Different number of links (ozon={len(oz_links)}, wb={len(wb_links)}). "
            "Pairs will be truncated to the shorter list."
        )

    oz_records = download_pages(
        links=oz_links,
        output_dir=args.oz_html_dir,
        profile_dir=args.profile_dir,
        browser_path=args.browser_path,
        headless=args.headless,
        per_page_delay=max(0.0, args.delay),
        timeout=max(10, args.timeout),
        overwrite=args.overwrite,
        manual_confirm=args.manual_confirm,
        skip_html=args.skip_html,
    )
    wb_records = parse_wb_links(wb_links)

    rows = _zip_pairs(oz_records, wb_records, oz_links, wb_links)
    if not rows:
        raise SystemExit("No paired rows were produced.")
    _write_rows(rows, args.out)
    print(f"[CSV] Saved {len(rows)} paired rows to {args.out}")

if __name__ == "__main__":
    main()
