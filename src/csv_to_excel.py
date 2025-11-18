import argparse
import csv
from pathlib import Path

from openpyxl import Workbook
from openpyxl.utils import get_column_letter
from openpyxl.styles import Alignment


def autosize(ws):
    for column_cells in ws.columns:
        length = max(len(str(cell.value)) if cell.value else 0 for cell in column_cells)
        ws.column_dimensions[get_column_letter(column_cells[0].column)].width = min(max(length + 2, 12), 80)


def convert_csv_to_xlsx(source: Path, target: Path) -> None:
    with source.open(encoding="utf-8") as fh:
        reader = csv.reader(fh)
        rows = list(reader)

    wb = Workbook()
    ws = wb.active
    ws.title = target.stem
    for row in rows:
        ws.append(row)

    for row in ws.iter_rows():
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")

    autosize(ws)
    target.parent.mkdir(parents=True, exist_ok=True)
    wb.save(target)
    print(f"Saved Excel to {target}")


def main():
    parser = argparse.ArgumentParser(description="Convert UTF-8 CSV to Excel (.xlsx).")
    parser.add_argument("--input", type=Path, required=True, help="Path to source CSV (UTF-8).")
    parser.add_argument("--out", type=Path, required=True, help="Output .xlsx path.")
    args = parser.parse_args()
    convert_csv_to_xlsx(args.input, args.out)


if __name__ == "__main__":
    main()
