import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


SCRIPT_JSON_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)
CANONICAL_LINK_RE = re.compile(
    r'<link[^>]+rel=["\']canonical["\'][^>]*href=["\']([^"\']+)["\']',
    re.IGNORECASE,
)
META_URL_RE = re.compile(
    r'<meta[^>]+property=["\']og:url["\'][^>]*content=["\']([^"\']+)["\']',
    re.IGNORECASE,
)
WILDBERRIES_ID_RE = re.compile(r"/catalog/(\d+)/")
OZON_ID_RE = re.compile(r"-(\d+)(?:/?|\.)")


@dataclass
class ProductRecord:
    vendor: str
    product_id: str
    url: Optional[str]
    name: Optional[str]
    brand: Optional[str]
    description: Optional[str]
    price: Optional[float]
    currency: Optional[str]
    availability: Optional[str]
    rating_value: Optional[float]
    review_count: Optional[int]
    images: List[str]
    raw_ld_json: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _load_json_candidates(html: str) -> Iterable[Dict[str, Any]]:
    for block in SCRIPT_JSON_RE.findall(html):
        text = block.strip()
        if not text:
            continue
        for candidate in _split_possible_json(text):
            try:
                parsed = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            yield parsed


def _split_possible_json(raw: str) -> Iterable[str]:
    raw = raw.strip()
    if not raw:
        return []
    if raw[0] in "[{":
        return [raw]
    parts: List[str] = []
    buf: List[str] = []
    depth = 0
    for ch in raw:
        buf.append(ch)
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth = max(0, depth - 1)
            if depth == 0:
                parts.append("".join(buf))
                buf.clear()
    if buf and buf[0] == "{":
        parts.append("".join(buf))
    return parts or [raw]


def _normalize_product_type(data: Any) -> Optional[str]:
    if isinstance(data, str):
        return data.lower()
    if isinstance(data, list):
        for item in data:
            normalized = _normalize_product_type(item)
            if normalized:
                return normalized
    return None


def _find_product_block(html: str) -> Optional[Dict[str, Any]]:
    for data in _load_json_candidates(html):
        if isinstance(data, list):
            for node in data:
                if isinstance(node, dict) and _normalize_product_type(node.get("@type")) == "product":
                    return node
            continue
        if isinstance(data, dict) and _normalize_product_type(data.get("@type")) == "product":
            return data
    return None


def _extract_url(html: str) -> Optional[str]:
    for pattern in (CANONICAL_LINK_RE, META_URL_RE):
        match = pattern.search(html)
        if match:
            return match.group(1)
    return None


def _ensure_list(value: Any) -> List[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


def _safe_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _extract_common_fields(vendor: str, html: str) -> ProductRecord:
    block = _find_product_block(html) or {}
    offers = block.get("offers") if isinstance(block.get("offers"), dict) else {}
    rating = block.get("aggregateRating") if isinstance(block.get("aggregateRating"), dict) else {}

    url = block.get("url") or _extract_url(html)
    product_id = _guess_product_id(vendor, url) or str(block.get("sku") or block.get("productID") or "")

    return ProductRecord(
        vendor=vendor,
        product_id=product_id,
        url=url,
        name=block.get("name"),
        brand=_extract_brand(block.get("brand")),
        description=block.get("description"),
        price=_safe_float(offers.get("price")),
        currency=offers.get("priceCurrency"),
        availability=offers.get("availability"),
        rating_value=_safe_float(rating.get("ratingValue")),
        review_count=_safe_int(rating.get("reviewCount")),
        images=_ensure_list(block.get("image")),
        raw_ld_json=block,
    )


def _extract_brand(value: Any) -> Optional[str]:
    if isinstance(value, dict):
        return value.get("name")
    if isinstance(value, list):
        for item in value:
            brand = _extract_brand(item)
            if brand:
                return brand
    if isinstance(value, str):
        return value
    return None


def _guess_product_id(vendor: str, url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    if vendor == "wildberries":
        match = WILDBERRIES_ID_RE.search(url.lower())
        if match:
            return match.group(1)
    elif vendor == "ozon":
        ids = OZON_ID_RE.findall(url.lower())
        if ids:
            return ids[-1]
    digits = re.findall(r"(\d{6,})", url)
    return digits[-1] if digits else None


def parse_file(path: Path, vendor: str) -> ProductRecord:
    html = path.read_text(encoding="utf-8", errors="ignore")
    vendor_key = vendor.lower()
    if vendor_key not in {"wildberries", "ozon"}:
        raise ValueError(f"Unsupported vendor: {vendor}")
    return _extract_common_fields(vendor_key, html)


def parse_directory(html_dir: Path, vendor: str) -> List[ProductRecord]:
    records: List[ProductRecord] = []
    for file_path in sorted(html_dir.glob("*.html")):
        try:
            records.append(parse_file(file_path, vendor))
        except Exception as exc:  # pylint: disable=broad-except
            print(f"[WARN] Failed to parse {file_path.name}: {exc}")
    return records
