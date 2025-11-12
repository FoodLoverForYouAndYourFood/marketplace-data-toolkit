import argparse
import csv
from pathlib import Path
from typing import List

from marketplace_parser import ProductRecord, parse_directory


def write_csv(records: List[ProductRecord], output: Path) -> None:
    if not records:
        print("No records parsed.")
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "vendor",
        "product_id",
        "url",
        "name",
        "brand",
        "description",
        "price",
        "currency",
        "availability",
        "rating_value",
        "review_count",
        "images",
    ]
    with output.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            writer.writerow(
                {
                    "vendor": record.vendor,
                    "product_id": record.product_id,
                    "url": record.url,
                    "name": record.name,
                    "brand": record.brand,
                    "description": record.description,
                    "price": record.price,
                    "currency": record.currency,
                    "availability": record.availability,
                    "rating_value": record.rating_value,
                    "review_count": record.review_count,
                    "images": "|".join(record.images),
                }
            )
    print(f"Saved {len(records)} rows to {output}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Parse cached HTML files into CSV.")
    parser.add_argument("--vendor", required=True, choices=["ozon", "wildberries"])
    parser.add_argument("--html-dir", type=Path, required=True, help="Directory with *.html files.")
    parser.add_argument("--out", type=Path, required=True, help="Path to CSV output.")
    args = parser.parse_args()

    records = parse_directory(args.html_dir, args.vendor)
    write_csv(records, args.out)


if __name__ == "__main__":
    main()
