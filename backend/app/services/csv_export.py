"""CSV output that is safe to open in a spreadsheet."""

import csv
import io
from collections.abc import Iterable, Sequence

# A cell starting with one of these is read by Excel, Sheets and LibreOffice as a formula, so text
# an attacker controls (a name, a title) could run commands or leak data when someone opens the
# file. OWASP's recommended defence is a leading apostrophe, which spreadsheets show as plain text.
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def safe_cell(value: object) -> str:
    text = "" if value is None else str(value)
    return f"'{text}" if text.startswith(_FORMULA_PREFIXES) else text


def to_csv(header: Sequence[str], rows: Iterable[Sequence[object]]) -> str:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\r\n")
    writer.writerow(header)
    for row in rows:
        writer.writerow([safe_cell(cell) for cell in row])
    return out.getvalue()
