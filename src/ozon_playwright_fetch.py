import argparse
import sys
import time
from pathlib import Path
from typing import Iterable, List, Optional

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


def read_links(path: Path) -> List[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [
        line.strip()
        for line in lines
        if line.strip() and not line.strip().startswith("#")
    ]


def guess_filename(url: str, index: int) -> str:
    lower = url.lower()
    parts = [segment for segment in lower.split("/") if segment.isdigit()]
    if parts:
        return parts[-1]
    digits = "".join(ch if ch.isdigit() else " " for ch in lower).split()
    if digits:
        return digits[-1]
    return f"page_{index:04d}"


def save_html(content: str, output_dir: Path, base_name: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / f"{base_name}.html"
    target.write_text(content, encoding="utf-8")
    return target


def download_pages(
    links: Iterable[str],
    output_dir: Path,
    profile_dir: Path,
    browser_path: Optional[Path],
    headless: bool,
    per_page_delay: float,
    timeout: int,
    overwrite: bool,
) -> None:
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

    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(**launch_kwargs)
        if browser.pages:
            page = browser.pages[0]
        else:
            page = browser.new_page()

        for idx, url in enumerate(links, 1):
            name = guess_filename(url, idx)
            target = output_dir / f"{name}.html"
            if target.exists() and not overwrite:
                print(f"[SKIP] {url} -> {target.name} (already exists)")
                continue
            print(f"[LOAD] {url}")
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
                print("  Разреши капчу/авторизацию при необходимости, затем нажми Enter...")
                input()
                if per_page_delay > 0:
                    time.sleep(per_page_delay)
                html = page.content()
                save_html(html, output_dir, name)
                print(f"[OK] saved {target}")
            except PlaywrightTimeoutError:
                print(f"[TIMEOUT] {url}", file=sys.stderr)
            except Exception as exc:  # pylint: disable=broad-except
                print(f"[ERROR] {url}: {exc}", file=sys.stderr)
        browser.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Download Ozon product HTML pages using your existing Opera/Chrome profile."
    )
    parser.add_argument("--links", type=Path, required=True, help="Text file with Ozon product links.")
    parser.add_argument("--out-dir", type=Path, required=True, help="Directory to store *.html files.")
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
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    links = read_links(args.links)
    if not links:
        print("No links found.", file=sys.stderr)
        raise SystemExit(1)

    download_pages(
        links=links,
        output_dir=args.out_dir,
        profile_dir=args.profile_dir,
        browser_path=args.browser_path,
        headless=args.headless,
        per_page_delay=max(0.0, args.delay),
        timeout=max(10, args.timeout),
        overwrite=args.overwrite,
    )


if __name__ == "__main__":
    main()
