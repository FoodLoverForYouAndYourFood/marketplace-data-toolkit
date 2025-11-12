import argparse
import csv
from pathlib import Path
from typing import List


def load_rows(path: Path, url_field: str, price_field: str) -> List[dict]:
    rows: List[dict] = []
    with path.open(encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            url = row.get(url_field)
            price = row.get(price_field)
            if not url:
                continue
            rows.append({"url": url, "price": price or ""})
    return rows


def save_rows(rows: List[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["url", "price"])
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract (url, price) pairs from any CSV.")
    parser.add_argument("--input", type=Path, required=True, help="Source CSV file.")
    parser.add_argument("--url-column", required=True, help="Name of the column with links.")
    parser.add_argument("--price-column", required=True, help="Name of the column with prices.")
    parser.add_argument("--out", type=Path, required=True, help="Destination CSV.")
    args = parser.parse_args()

    rows = load_rows(args.input, args.url_column, args.price_column)
    save_rows(rows, args.out)
    print(f"Saved {len(rows)} rows to {args.out}")


if __name__ == "__main__":
    main()
