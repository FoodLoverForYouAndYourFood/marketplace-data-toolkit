import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional
from urllib.parse import quote, urlsplit

from curl_cffi import requests as curl_requests
import requests as std_requests


def read_links(path: Path) -> List[str]:
    if not path or not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    return [
        line.strip()
        for line in lines
        if line.strip() and not line.strip().startswith("#")
    ]


def _ensure_list(value: Optional[Iterable[str]]) -> List[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


def _safe_float(value: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(str(value).replace(" ", "").replace(",", "."))
    except ValueError:
        return None


def _safe_int(value: Optional[str]) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(float(value))
    except ValueError:
        return None


def _extract_brand(value) -> Optional[str]:
    if isinstance(value, dict):
        return value.get("name") or value.get("brand")
    if isinstance(value, list):
        for item in value:
            brand = _extract_brand(item)
            if brand:
                return brand
    if isinstance(value, str):
        return value
    return None


def parse_ozon_links(links: List[str], cookies_path: Optional[Path] = None) -> List[Dict[str, Optional[str]]]:
    if not links:
        return []

    session = curl_requests.Session(impersonate="chrome124")
    session.headers.update(
        {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            "Origin": "https://www.ozon.ru",
            "Referer": "https://www.ozon.ru/",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "x-o3-app-name": "ozon-app-web",
            "x-o3-app-version": "d0.0.0",
            "x-o3-channel": "web",
            "x-o3-device-type": "pc",
            "x-o3-geo-region-id": "213",
            "x-o3-language": "ru",
        }
    )
    cookie_lookup = {}
    if cookies_path:
        cookies = load_cookies(cookies_path)
        for cookie in cookies:
            name = cookie.get("name")
            value = cookie.get("value")
            if not name or value is None:
                continue
            cookie_lookup[name] = value
            session.cookies.set(
                name,
                value,
                domain=cookie.get("domain", ".ozon.ru"),
                path=cookie.get("path", "/"),
            )
    if "__Secure-access-token" in cookie_lookup:
        session.headers["Authorization"] = f"Bearer {cookie_lookup['__Secure-access-token']}"
    if "rfuid" in cookie_lookup:
        session.headers["x-o3-device-id"] = cookie_lookup["rfuid"]
    if "xcid" in cookie_lookup:
        session.headers["x-o3-session-id"] = cookie_lookup["xcid"]
    session.get("https://www.ozon.ru", timeout=30)

    records: List[Dict[str, Optional[str]]] = []
    for link in links:
        rel = _ozon_relative(link)
        if not rel:
            continue
        encoded = quote(rel, safe="/:")
        api_url = f"https://www.ozon.ru/api/composer-api.bx/page/json/v2?url={encoded}"
        try:
            resp = session.get(api_url, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:  # pylint: disable=broad-except
            print(f"[OZON][FAIL] {link}: {exc}")
            continue

        seo_scripts = data.get("seo", {}).get("script", [])
        if not seo_scripts:
            print(f"[OZON][MISS] {link}: no SEO script")
            continue
        try:
            ld_json = json.loads(seo_scripts[0]["innerHTML"])
        except (json.JSONDecodeError, KeyError) as exc:
            print(f"[OZON][MISS] {link}: bad JSON ({exc})")
            continue

        offers = ld_json.get("offers") or {}
        rating = ld_json.get("aggregateRating") or {}

        record = {
            "vendor": "ozon",
            "product_id": str(ld_json.get("sku") or data.get("widgetStates", {}).get("webProductId") or ""),
            "url": link,
            "name": ld_json.get("name") or data.get("seo", {}).get("title"),
            "brand": _extract_brand(ld_json.get("brand")),
            "description": ld_json.get("description"),
            "price": _safe_float(offers.get("price")),
            "currency": offers.get("priceCurrency"),
            "rating_value": _safe_float(rating.get("ratingValue")),
            "review_count": _safe_int(rating.get("reviewCount")),
            "images": "|".join(_ensure_list(ld_json.get("image"))),
            "supplier_id": None,
            "supplier_name": None,
            "subject_id": None,
        }
        records.append(record)
        print(f"[OZON][OK] {record['product_id']} {record['name']}")
    return records


def _ozon_relative(link: str) -> Optional[str]:
    if not link:
        return None
    parsed = urlsplit(link)
    if "ozon" not in parsed.netloc:
        return None
    path = parsed.path or ""
    query = f"?{parsed.query}" if parsed.query else ""
    return path + query


WB_ID_RE = re.compile(r"/catalog/(\d+)/")


def parse_wb_links(
    links: List[str],
    on_progress: Optional[Callable[[int, int, str], None]] = None,
) -> List[Dict[str, Optional[str]]]:
    if not links:
        return []
    records: List[Dict[str, Optional[str]]] = []
    total = len(links)
    for idx, link in enumerate(links, 1):
        product_id = _extract_wb_id(link)
        if not product_id:
            print(f"[WB][MISS] {link}: cannot find product id")
            if on_progress:
                on_progress(idx, total, link)
            continue
        params = {
            "appType": 1,
            "curr": "rub",
            "dest": "-1257786",
            "spp": 30,
            "nm": product_id,
        }
        try:
            resp = std_requests.get("https://card.wb.ru/cards/v2/detail", params=params, timeout=30)
            resp.raise_for_status()
            payload = resp.json()
        except Exception as exc:  # pylint: disable=broad-except
            print(f"[WB][FAIL] {product_id}: {exc}")
            continue

        products = payload.get("data", {}).get("products") or []
        if not products:
            print(f"[WB][MISS] {product_id}: empty data")
            if on_progress:
                on_progress(idx, total, link)
            continue
        item = products[0]
        price = _wb_price(item)

        record = {
            "vendor": "wildberries",
            "product_id": str(item.get("id") or product_id),
            "url": link,
            "name": item.get("name"),
            "brand": item.get("brand"),
            "description": item.get("description"),
            "price": price,
            "currency": "RUB",
            "rating_value": _safe_float(item.get("reviewRating")),
            "review_count": _safe_int(item.get("feedbacks")),
            "images": "|".join(_wb_images(item)),
            "supplier_id": str(item.get("supplierId") or ""),
            "supplier_name": item.get("supplier"),
            "subject_id": str(item.get("subjectId") or ""),
        }
        records.append(record)
        print(f"[WB][OK] {record['product_id']} {record['name']}")
        if on_progress:
            on_progress(idx, total, link)
    return records


def _extract_wb_id(link: str) -> Optional[str]:
    match = WB_ID_RE.search(link)
    if match:
        return match.group(1)
    digits = re.findall(r"(\d{6,})", link)
    return digits[-1] if digits else None


def _wb_images(item: Dict[str, Any]) -> List[str]:
    photos = item.get("photos") or []
    result = []
    for photo in photos[:10]:
        name = photo.get("full") or photo.get("big") or photo.get("tm")
        if not name:
            continue
        result.append(f"https://images.wbstatic.net/{name}")
    return result


def _wb_price(item: Dict[str, Any]) -> Optional[float]:
    sizes = item.get("sizes") or []
    if not sizes:
        return None
    price_info = sizes[0].get("price") or {}
    for key in ("product", "total", "basic"):
        value = price_info.get(key)
        if isinstance(value, (int, float)) and value > 0:
            return round(value / 100, 2)
    return None


def load_cookies(path: Path) -> List[Dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
    except Exception as exc:  # pylint: disable=broad-except
        print(f"[COOKIES] Failed to load {path}: {exc}")
    return []


def write_csv(records: List[Dict[str, Optional[str]]], out_path: Path) -> None:
    if not records:
        print("No records to write.")
        return
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "vendor",
        "product_id",
        "url",
        "name",
        "brand",
        "description",
        "price",
        "currency",
        "rating_value",
        "review_count",
        "images",
        "supplier_id",
        "supplier_name",
        "subject_id",
    ]
    with out_path.open("w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            writer.writerow(record)
    print(f"Saved {len(records)} rows to {out_path}")


def build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fetch product data from GitHub-proven endpoints (Ozon composer API + WB card API)."
    )
    parser.add_argument("--oz-links", type=Path, help="Text file with Ozon product links.")
    parser.add_argument("--wb-links", type=Path, help="Text file with Wildberries product links.")
    parser.add_argument("--out", type=Path, default=Path("products.csv"), help="Output CSV path.")
    parser.add_argument("--ozon-cookies", type=Path, help="Path to JSON file with Ozon cookies.")
    return parser


def main() -> None:
    parser = build_cli()
    args = parser.parse_args()

    all_records: List[Dict[str, Optional[str]]] = []

    ozon_links = read_links(args.oz_links) if args.oz_links else []
    if ozon_links:
        all_records.extend(parse_ozon_links(ozon_links, cookies_path=args.ozon_cookies))

    wb_links = read_links(args.wb_links) if args.wb_links else []
    if wb_links:
        all_records.extend(parse_wb_links(wb_links))

    if not all_records:
        print("Nothing was parsed. Check input files.")
        return
    write_csv(all_records, args.out)


if __name__ == "__main__":
    main()
