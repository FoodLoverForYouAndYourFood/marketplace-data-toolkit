import argparse
import csv
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Callable, Iterable, List, Optional, Tuple
from urllib.parse import urlsplit

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


def read_links(path: Path) -> List[str]:
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


@dataclass
class PriceRecord:
    url: str
    product_id: str
    name: Optional[str]
    price_with_card: Optional[str]
    price_without_card: Optional[str]
    timestamp: str

    def to_row(self) -> dict:
        return {
            "url": self.url,
            "product_id": self.product_id,
            "name": self.name or "",
            "price_with_card": self.price_with_card or "",
            "price_without_card": self.price_without_card or "",
            "timestamp": self.timestamp,
        }


def extract_ozon_id(url: str) -> Optional[str]:
    parsed = urlsplit(url)
    if "ozon.ru" not in parsed.netloc or not parsed.path:
        return None
    slug = parsed.path.rstrip("/").split("/")[-1]
    slug = slug.split("?")[0]
    for part in reversed(slug.split("-")):
        if part.isdigit():
            return part
    return None


def guess_filename(url: str, index: int) -> str:
    product_id = extract_ozon_id(url)
    if product_id:
        return product_id
    digits = "".join(ch if ch.isdigit() else " " for ch in url).split()
    if digits:
        return digits[-1]
    return f"page_{index:04d}"


def save_html(content: str, output_dir: Path, base_name: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / f"{base_name}.html"
    target.write_text(content, encoding="utf-8")
    return target


def _normalize_label_text(text: str) -> str:
    normalized = (
        text.replace("\u2009", " ")
        .replace("\xa0", " ")
        .replace("ё", "е")
        .strip()
        .lower()
    )
    return re.sub(r"\s+", " ", normalized)


def _extract_price_candidate(text: str) -> Optional[str]:
    if "₽" not in text and "руб" not in text.lower():
        return None
    cleaned = (
        text.replace("\u2009", "")
        .replace("\xa0", "")
        .replace("₽", "")
        .replace("руб.", "")
        .replace("руб", "")
    )
    cleaned = re.sub(r"[^\d,\.]", "", cleaned).replace(",", ".")
    match = re.search(r"\d+(?:\.\d+)?", cleaned)
    return match.group(0) if match else None


def _normalize_price_value(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    try:
        value = Decimal(raw)
    except InvalidOperation:
        return None
    normalized = value.normalize()
    text = format(normalized, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def _find_price_before_label(lines: List[str], predicate) -> Optional[str]:
    for idx, line in enumerate(lines):
        if predicate(_normalize_label_text(line)):
            for candidate in reversed(lines[:idx]):
                price = _extract_price_candidate(candidate)
                if price:
                    return price
            break
    return None


def extract_prices_from_text(text_block: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    if not text_block:
        return None, None
    lines = [line.strip() for line in text_block.splitlines() if line.strip()]
    with_card = _find_price_before_label(
        lines,
        lambda value: "ozon" in value and "карт" in value and "без" not in value,
    )
    without_card = _find_price_before_label(
        lines,
        lambda value: "без" in value and "ozon" in value and "карт" in value,
    )
    return _normalize_price_value(with_card), _normalize_price_value(without_card)


def extract_prices_from_page(page) -> Tuple[Optional[str], Optional[str]]:
    try:
        block_text = page.inner_text("[data-widget='webPrice']")
    except Exception:  # noqa: BLE001 - best effort extraction
        block_text = None
    return extract_prices_from_text(block_text)


def extract_product_name(page) -> Optional[str]:
    for selector in ("h1", "[data-widget='webProductHeading'] h1"):
        try:
            name = page.inner_text(selector)
            if name:
                return name.strip()
        except Exception:  # noqa: BLE001
            continue
    try:
        return page.title()
    except Exception:  # noqa: BLE001
        return None

def is_out_of_stock(page) -> bool:
    """Detect out-of-stock page quickly to skip long waits."""
    try:
        body_text = page.inner_text("body")
    except Exception:  # noqa: BLE001
        return False
    lowered = body_text.lower()
    return "товар закончился" in lowered or "нет в наличии" in lowered


def write_csv_report(records: List[PriceRecord], csv_path: Path) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["url", "product_id", "name", "price_with_card", "price_without_card", "timestamp"]
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            writer.writerow(record.to_row())


def download_pages(
    links: Iterable[str],
    output_dir: Path,
    profile_dir: Path,
    browser_path: Optional[Path],
    headless: bool,
    per_page_delay: float,
    timeout: int,
    overwrite: bool,
    manual_confirm: bool,
    skip_html: bool,
    on_progress: Optional[Callable[[int, int, str, str], None]] = None,
) -> List[PriceRecord]:
    links_list = list(links)
    total = len(links_list)
    launch_kwargs = {
        "user_data_dir": str(profile_dir),
        "headless": headless,
        "args": [
            "--disable-blink-features=AutomationControlled",
            "--disable-extensions",
            "--disable-gpu",
        ],
    }
    if browser_path:
        launch_kwargs["executable_path"] = str(browser_path)

    records: List[PriceRecord] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch_persistent_context(**launch_kwargs)
        page = browser.pages[0] if browser.pages else browser.new_page()

        for idx, url in enumerate(links_list, 1):
            name = guess_filename(url, idx)
            target = output_dir / f"{name}.html"
            status = "ok"

            print(f"[LOAD] {url}")
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
                if manual_confirm:
                    input("  Press Enter after verifying the page is ready...")
                if is_out_of_stock(page):
                    status = "out_of_stock"
                    print(f"[SKIP] out of stock: {url}")
                    per_page_sleep = min(0.2, per_page_delay)
                else:
                    per_page_sleep = per_page_delay
                if per_page_sleep > 0:
                    time.sleep(per_page_delay)

                if not skip_html:
                    if target.exists() and not overwrite:
                        print(f"[HTML] skip overwrite for {target.name}")
                    else:
                        save_html(page.content(), output_dir, name)
                        print(f"[HTML] saved {target}")

                price_with_card, price_without_card = extract_prices_from_page(page) if status != "out_of_stock" else (None, None)
                record = PriceRecord(
                    url=url,
                    product_id=extract_ozon_id(url) or name,
                    name=extract_product_name(page),
                    price_with_card=price_with_card,
                    price_without_card=price_without_card,
                    timestamp=datetime.now().isoformat(timespec="seconds"),
                )
                records.append(record)
                print(
                    f"[PRICE] card={price_with_card or 'n/a'} | no-card={price_without_card or 'n/a'}"
                )
            except PlaywrightTimeoutError:
                status = "timeout"
                print(f"[TIMEOUT] {url}", file=sys.stderr)
            except Exception as exc:  # pylint: disable=broad-except
                status = "error"
                print(f"[ERROR] {url}: {exc}", file=sys.stderr)
            finally:
                if on_progress:
                    safe_total = total or len(links_list) or 1
                    on_progress(min(idx, safe_total), safe_total, url, status)

        browser.close()
    return records


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fetch Ozon product pages via Playwright and export price snapshots to CSV."
    )
    default_html_dir = Path("output") / "html" / "ozon"
    default_html_str = str(default_html_dir)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    default_csv = Path("output") / f"ozon_prices_{timestamp}.csv"
    default_csv_str = str(default_csv)
    parser.add_argument("--links", type=Path, required=True, help="Text file with Ozon product links.")
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=default_html_dir,
        help=f"Directory to store *.html files (default: {default_html_str}).",
    )
    parser.add_argument(
        "--profile-dir",
        type=Path,
        required=True,
        help="Path to browser profile (close browser before running).",
    )
    parser.add_argument(
        "--browser-path",
        type=Path,
        help="Optional path to Opera/Chrome executable. If omitted, Playwright's bundled Chromium is used.",
    )
    parser.add_argument("--headless", action="store_true", help="Run browser headless (not recommended).")
    parser.add_argument("--delay", type=float, default=1.5, help="Seconds to wait after each load.")
    parser.add_argument("--timeout", type=int, default=90, help="Navigation timeout (seconds).")
    parser.add_argument("--overwrite", action="store_true", help="Rewrite existing HTML files.")
    parser.add_argument(
        "--manual-confirm",
        action="store_true",
        help="Require manual confirmation (press Enter) after each navigation.",
    )
    parser.add_argument(
        "--csv-out",
        type=Path,
        default=default_csv,
        help=f"Path for the resulting CSV (default: {default_csv_str}).",
    )
    parser.add_argument(
        "--skip-html",
        action="store_true",
        help="Do not store HTML snapshots (still fetches prices).",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    links = read_links(args.links)
    if not links:
        print("No links found.", file=sys.stderr)
        raise SystemExit(1)

    records = download_pages(
        links=links,
        output_dir=args.out_dir,
        profile_dir=args.profile_dir,
        browser_path=args.browser_path,
        headless=args.headless,
        per_page_delay=max(0.0, args.delay),
        timeout=max(10, args.timeout),
        overwrite=args.overwrite,
        manual_confirm=args.manual_confirm,
        skip_html=args.skip_html,
    )
    write_csv_report(records, args.csv_out)
    print(f"[CSV] Saved {len(records)} rows to {args.csv_out}")


if __name__ == "__main__":
    main()
