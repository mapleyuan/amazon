from __future__ import annotations

import csv
import io
from zipfile import ZipFile, ZIP_DEFLATED

from app.db.connection import get_connection
from app.jobs.repository import log_export
from app.ranking.query_service import query_ranks

HEADERS = [
    "job_id",
    "snapshot_date",
    "site",
    "board_type",
    "category_name",
    "category_key",
    "asin",
    "rank",
    "title",
    "brand",
    "price_text",
    "rating",
    "review_count",
    "image_url",
    "detail_url",
]


def export_ranks_csv(filters: dict) -> str:
    payload = query_ranks({**filters, "page": 1, "page_size": 50000})
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=HEADERS)
    writer.writeheader()

    for row in payload["items"]:
        writer.writerow({key: row.get(key) for key in HEADERS})

    conn = get_connection()
    log_export(conn, file_type="csv", filters=filters)
    return output.getvalue()


def _col_name(index: int) -> str:
    name = ""
    while index > 0:
        index, rem = divmod(index - 1, 26)
        name = chr(ord("A") + rem) + name
    return name


def _xlsx_sheet_xml(rows: list[list[str]], shared_map: dict[str, int]) -> str:
    lines = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">',
        "<sheetData>",
    ]

    for ridx, row in enumerate(rows, start=1):
        lines.append(f'<row r="{ridx}">')
        for cidx, value in enumerate(row, start=1):
            ref = f"{_col_name(cidx)}{ridx}"
            sid = shared_map[value]
            lines.append(f'<c r="{ref}" t="s"><v>{sid}</v></c>')
        lines.append("</row>")

    lines.extend(["</sheetData>", "</worksheet>"])
    return "".join(lines)


def _xlsx_shared_strings_xml(values: list[str]) -> str:
    parts = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        (
            '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            f'count="{len(values)}" uniqueCount="{len(values)}">'
        ),
    ]

    for value in values:
        escaped = (
            value.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )
        parts.append(f"<si><t>{escaped}</t></si>")
    parts.append("</sst>")
    return "".join(parts)


def export_ranks_xlsx(filters: dict) -> bytes:
    payload = query_ranks({**filters, "page": 1, "page_size": 50000})
    rows = [HEADERS]

    for item in payload["items"]:
        rows.append([str(item.get(header, "")) for header in HEADERS])

    unique_values: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for value in row:
            if value not in seen:
                seen.add(value)
                unique_values.append(value)
    shared_map = {value: idx for idx, value in enumerate(unique_values)}

    sheet_xml = _xlsx_sheet_xml(rows, shared_map)
    shared_xml = _xlsx_shared_strings_xml(unique_values)

    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>
</Types>"""

    rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>"""

    workbook = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="Ranks" sheetId="1" r:id="rId1"/>
  </sheets>
</workbook>"""

    workbook_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings" Target="sharedStrings.xml"/>
</Relationships>"""

    buf = io.BytesIO()
    with ZipFile(buf, "w", compression=ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("xl/workbook.xml", workbook)
        zf.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        zf.writestr("xl/worksheets/sheet1.xml", sheet_xml)
        zf.writestr("xl/sharedStrings.xml", shared_xml)

    conn = get_connection()
    log_export(conn, file_type="xlsx", filters=filters)
    return buf.getvalue()
