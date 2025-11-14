import argparse
import csv
from datetime import datetime
from pathlib import Path
from typing import List, Sequence, Tuple

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
        oz_price = oz.price_with_card or oz.price_without_card
        rows.append(
            {
                "name": oz.name or wb.get("name") or "",
                "ozon_url": oz_links[idx],
                "wb_url": wb_links[idx],
                "price": oz_price if oz_price else (str(wb_price) if wb_price is not None else ""),
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
                "price",
                "wb_article",
                "parsed_at",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)


def build_cli() -> argparse.ArgumentParser:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    default_out = Path("output") / f"paired_prices_{timestamp}.csv"
    parser = argparse.ArgumentParser(
        description="Fetch paired Ozon+WB prices (1:1 order) and build a combined CSV."
    )
    parser.add_argument("--oz-links", type=Path, required=True, help="File with Ozon links.")
    parser.add_argument("--wb-links", type=Path, required=True, help="File with WB links.")
    parser.add_argument(
        "--profile-dir",
        type=Path,
        required=True,
        help="Browser profile directory with an authenticated Ozon session.",
    )
    parser.add_argument(
        "--browser-path",
        type=Path,
        help="Optional browser executable path (Chrome/Chromium).",
    )
    parser.add_argument(
        "--oz-html-dir",
        type=Path,
        default=Path("output/html/ozon"),
        help="Where to store temporary Ozon HTML snapshots (default: output/html/ozon).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=default_out,
        help=f"Destination CSV (default: {default_out}).",
    )
    parser.add_argument("--headless", action="store_true", help="Run browser headless.")
    parser.add_argument("--delay", type=float, default=1.5, help="Delay between pages (seconds).")
    parser.add_argument("--timeout", type=int, default=90, help="Navigation timeout (seconds).")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite HTML snapshots if saved.")
    parser.add_argument(
        "--manual-confirm",
        action="store_true",
        help="Pause after each navigation until Enter is pressed.",
    )
    parser.add_argument(
        "--skip-html",
        action="store_true",
        help="Do not write HTML snapshots to disk.",
    )
    return parser


def main() -> None:
    parser = build_cli()
    args = parser.parse_args()

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
