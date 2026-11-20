"""create_spreadsheet: arma un archivo Excel (.xlsx) con los datos que le pase el modelo.

Dos formatos en la misma tool:
- Tabla simple (solo headers + rows): encabezado fijo y filtros, para listas.
- Documento (con title/info/totals/notes): factura, recibo, estado de cuenta.
  Título del comercio, bloque de datos del encabezado, tabla de líneas con
  formato de moneda, resumen de totales con el total resaltado y notas.

El archivo se guarda en Documentos\\ATLAS sin pisar nada y se devuelve como
ToolFile para que el chat ofrezca descargarlo.
"""
from __future__ import annotations

import math
import os
import re
from datetime import datetime
from pathlib import Path

from app.core import outputs
from app.security.permissions import RiskLevel
from app.tools.base import Tool, ToolContext, ToolResult

MAX_SHEETS = 20
MAX_ROWS = 20000
MAX_COLUMNS = 200
FORMATS = ("text", "integer", "number", "currency", "percent")
_BAD_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_BAD_SHEETNAME = re.compile(r"[\[\]:*?/\\]")
# "1234", "-12.5", "1,234.50" → número. No se tocan códigos con ceros a la
# izquierda ("00123", un CP o un DNI), que en Excel perderían los ceros.
_NUMBER = re.compile(r"^-?(?:0|[1-9]\d{0,2}(?:,\d{3})+|[1-9]\d*)(?:\.\d+)?$")
_CURRENCY_PREFIX = re.compile(r"^(?:[A-Z]{0,3}\$|US\$|RD\$|€|£)\s*")

# Paleta del documento.
_DARK = "1F4E78"
_STRIPE = "EEF3F8"
_HIGHLIGHT = "FFF2CC"
_GREY = "808080"


def _number(text: str):
    """'1,234.50' / '$1,234.50' / 'RD$ 12' → número; si no parece número, None."""
    cleaned = _CURRENCY_PREFIX.sub("", text.strip())
    negative = cleaned.startswith("(") and cleaned.endswith(")")
    cleaned = cleaned.strip("()").strip()
    if not _NUMBER.match(cleaned):
        return None
    value = float(cleaned.replace(",", ""))
    if negative:
        value = -value
    return int(value) if value.is_integer() and "." not in cleaned else value


def _cell(value, fmt: str = "auto"):
    if isinstance(value, str):
        if value.startswith("="):  # fórmula de Excel
            return value
        if fmt == "text":
            return value
        number = _number(value)
        return value if number is None else number
    if value is None or isinstance(value, (int, float, bool)):
        return value
    return str(value)


def _number_format(fmt: str, symbol: str) -> str | None:
    return {
        "integer": "#,##0",
        "number": "#,##0.00",
        "currency": f'"{symbol}"#,##0.00;-"{symbol}"#,##0.00',
        "percent": "0.00%",
    }.get(fmt)


def _filename(raw: str) -> str:
    name = _BAD_FILENAME.sub("", (raw or "").strip()).strip(" .")
    if name.lower().endswith(".xlsx"):
        name = name[:-5]
    return (name[:100] or f"tabla-{datetime.now():%Y%m%d-%H%M%S}") + ".xlsx"


def _unique(path: Path) -> Path:
    if not path.exists():
        return path
    for n in range(2, 1000):
        candidate = path.with_name(f"{path.stem} ({n}){path.suffix}")
        if not candidate.exists():
            return candidate
    return path.with_name(f"{path.stem}-{datetime.now():%H%M%S%f}{path.suffix}")


def _shown_length(value, fmt: str) -> int:
    """Ancho aproximado en caracteres con el que Excel muestra la celda."""
    if value is None:
        return 0
    if isinstance(value, (int, float)) and not isinstance(value, bool) and fmt in ("number", "currency"):
        return len(f"{value:,.2f}") + (2 if fmt == "currency" else 0)
    if isinstance(value, str) and value.startswith("="):
        return 12
    return len(str(value))


class CreateSpreadsheetTool(Tool):
    name = "create_spreadsheet"
    description = (
        "Crea un archivo Excel (.xlsx) en Documentos/ATLAS y lo ofrece para descargar desde el chat. "
        "Usala cuando el usuario pida pasar a Excel una tabla, lista, factura, recibo o comprobante, por ejemplo "
        "de una imagen o PDF que adjuntó. Transcribí TODO tal cual aparece, sin resumir ni inventar.\n"
        "- Lista o tabla simple: solo 'headers' y 'rows'.\n"
        "- Factura / recibo / comprobante: armalo como documento. 'title' = nombre comercial; 'subtitle' = razón "
        "social y tipo de documento; 'info' = TODOS los datos del encabezado como pares etiqueta/valor (número de "
        "factura, número fiscal/NCF, condición de pago, RNC o identificación del comercio, identificación del "
        "cliente, cliente, vendedor, fecha de emisión...). Ningún valor vacío: una palabra suelta como 'CONTADO' es "
        "{label:'Condición', value:'CONTADO'}; un número suelto bajo la razón social es el RNC del comercio.\n"
        "- Tabla de líneas: si cada línea trae un código (ej. PR000095), va en su propia columna 'Código', separado "
        "de la descripción. Headers típicos: Código, Descripción, Cantidad, Precio unit., Subtotal, con "
        "'column_formats' ['text','text','number','currency','currency'].\n"
        "- 'totals' = cada línea de totales impresa (ITBIS/IVA con la tasa en 'detail', total impuesto, total "
        "factura, total cancelado, forma de pago con su monto), en el orden impreso, con highlight=true en TOTAL "
        "FACTURA (el total a pagar). Podés agregar 'Subtotal (sin impuestos)' con sum_of_column de la columna "
        "subtotal.\n"
        "- 'notes' = observaciones útiles: anotaciones a mano, diferencias entre lo impreso y lo calculado, moneda.\n"
        "ANTES de llamar, verificá: cantidad × precio = subtotal en cada línea, y suma de subtotales + impuesto = "
        "total. Si algo no cuadra, volvé a mirar la imagen (y sus recortes ampliados) y corregí la lectura; si "
        "sigue sin cuadrar, decilo en 'notes'. Leé los identificadores (RNC, NCF, números de factura) dígito por "
        "dígito en los recortes ampliados.\n"
        "Los números van como números (sin símbolo); la moneda va en 'currency_symbol'. Los identificadores "
        "(RNC, NCF, códigos) van como texto. No abras el archivo salvo que el usuario lo pida: el chat ya muestra "
        "el botón para descargarlo."
    )
    parameters = {
        "type": "object",
        "properties": {
            "filename": {"type": "string", "description": "Nombre del archivo, sin ruta (ej. 'Factura Bamby E310000000120')."},
            "currency_symbol": {"type": "string", "description": "Símbolo para las columnas y totales de moneda. Por defecto '$'."},
            "sheets": {
                "type": "array",
                "description": "Hojas del libro, en orden.",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Nombre de la hoja (máx. 31 caracteres)."},
                        "title": {"type": "string", "description": "Título grande arriba (ej. nombre del comercio)."},
                        "subtitle": {"type": "string", "description": "Línea bajo el título (razón social, tipo de documento)."},
                        "info": {
                            "type": "array",
                            "description": "Datos del encabezado del documento, en el orden en que aparecen.",
                            "items": {
                                "type": "object",
                                "properties": {"label": {"type": "string"}, "value": {"type": "string"}},
                                "required": ["label", "value"],
                            },
                        },
                        "headers": {"type": "array", "items": {"type": "string"}, "description": "Encabezados de columna."},
                        "column_formats": {
                            "type": "array",
                            "items": {"type": "string", "enum": list(FORMATS)},
                            "description": "Formato de cada columna, en el orden de headers.",
                        },
                        "rows": {
                            "type": "array",
                            "description": "Filas de datos; cada fila es una lista de celdas en el orden de los encabezados.",
                            "items": {"type": "array", "items": {"type": ["string", "number", "boolean", "null"]}},
                        },
                        "totals_title": {"type": "string", "description": "Título del bloque de totales. Por defecto 'Resumen de impuestos y totales'."},
                        "totals": {
                            "type": "array",
                            "description": "Líneas de totales bajo la tabla.",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "label": {"type": "string"},
                                    "value": {"type": ["number", "string", "null"], "description": "Monto o texto."},
                                    "detail": {"type": ["number", "string", "null"], "description": "Dato intermedio, ej. la tasa '18%'."},
                                    "sum_of_column": {"type": "integer", "description": "Si se indica, el valor es la fórmula SUMA de esa columna de la tabla (1 = primera)."},
                                    "highlight": {"type": "boolean", "description": "Resaltar (el total a pagar)."},
                                },
                                "required": ["label"],
                            },
                        },
                        "notes": {"type": "array", "items": {"type": "string"}, "description": "Notas al pie, una por elemento."},
                    },
                    "required": ["rows"],
                },
            },
            "open_after": {"type": "boolean", "description": "Abrir el archivo en Excel al terminar. Solo si el usuario lo pide."},
        },
        "required": ["filename", "sheets"],
    }
    risk_level = RiskLevel.LOW_RISK  # crea un archivo nuevo en una carpeta propia; nunca pisa uno existente

    def __init__(self, directory: Path | None = None) -> None:
        self._directory = directory

    def human_description(self, params: dict) -> str:
        return f"Crear el Excel '{_filename(str(params.get('filename', '')))}'"

    def execute(self, params: dict, context: ToolContext) -> ToolResult:
        try:
            from openpyxl import Workbook  # noqa: F401
        except ImportError:
            return ToolResult(success=False, error="Falta la librería openpyxl en el backend (pip install openpyxl).")

        sheets = params.get("sheets")
        if not isinstance(sheets, list) or not sheets:
            return ToolResult(success=False, error="No hay hojas con datos para guardar.")
        if len(sheets) > MAX_SHEETS:
            return ToolResult(success=False, error=f"Máximo {MAX_SHEETS} hojas por archivo.")
        if not all(isinstance(s, dict) for s in sheets):
            return ToolResult(success=False, error="Alguna hoja no tiene el formato esperado.")
        total_rows = sum(len(s.get("rows") or []) for s in sheets)
        if total_rows > MAX_ROWS:
            return ToolResult(success=False, error=f"Son demasiadas filas ({total_rows}); el máximo es {MAX_ROWS}.")

        symbol = str(params.get("currency_symbol") or "$").strip()[:5] or "$"
        workbook = _build_workbook(sheets, symbol)

        directory = self._directory or outputs.output_dir()
        try:
            directory.mkdir(parents=True, exist_ok=True)
            path = _unique(directory / _filename(str(params.get("filename", ""))))
            workbook.save(path)
        except OSError as exc:
            return ToolResult(success=False, error=f"No pude guardar el Excel: {exc}")

        summary = (
            f"Excel guardado en {path} ({total_rows} filas, {len(sheets)} hoja{'s' if len(sheets) != 1 else ''}). "
            "El chat ya muestra el archivo con botones para descargarlo o abrirlo."
        )
        if params.get("open_after"):
            try:
                os.startfile(path)  # noqa: S606 — archivo .xlsx recién creado por esta tool
                summary += " Además lo abrí en Excel."
            except (OSError, AttributeError) as exc:
                summary += f" No pude abrirlo automáticamente ({exc})."
        return ToolResult(success=True, data=summary, files=[outputs.describe(path)])


def _build_workbook(sheets: list[dict], symbol: str):
    from openpyxl import Workbook

    workbook = Workbook()
    workbook.remove(workbook.active)
    used: set[str] = set()
    for index, sheet in enumerate(sheets, start=1):
        title = _BAD_SHEETNAME.sub("", str(sheet.get("name") or sheet.get("title") or f"Hoja{index}")).strip()[:31] or f"Hoja{index}"
        base, n = title, 2
        while title.lower() in used:
            suffix = f" ({n})"
            title, n = base[: 31 - len(suffix)] + suffix, n + 1
        used.add(title.lower())
        _fill_sheet(workbook.create_sheet(title), sheet, symbol)
    return workbook


def _fill_sheet(ws, sheet: dict, symbol: str) -> None:
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    headers = [str(h) for h in (sheet.get("headers") or [])][:MAX_COLUMNS]
    rows = [r if isinstance(r, list) else [r] for r in (sheet.get("rows") or [])]
    rows = [r[:MAX_COLUMNS] for r in rows]
    table_width = max([len(headers)] + [len(r) for r in rows] + [1])
    raw_formats = [str(f) for f in (sheet.get("column_formats") or [])]
    formats = [(raw_formats[i] if i < len(raw_formats) and raw_formats[i] in FORMATS else "auto") for i in range(table_width)]
    info = [i for i in (sheet.get("info") or []) if isinstance(i, dict) and str(i.get("label", "")).strip()]
    totals = [t for t in (sheet.get("totals") or []) if isinstance(t, dict) and str(t.get("label", "")).strip()]
    notes = [str(n).strip() for n in (sheet.get("notes") or []) if str(n).strip()]
    document = bool(sheet.get("title") or sheet.get("subtitle") or info or totals or notes)

    thin = Side(style="thin", color="B7C4D1")
    medium = Side(style="medium", color=_DARK)
    grid = Border(left=thin, right=thin, top=thin, bottom=thin)
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor=_DARK)
    stripe_fill = PatternFill("solid", fgColor=_STRIPE)
    highlight_fill = PatternFill("solid", fgColor=_HIGHLIGHT)

    width = max(table_width, 4) if document else table_width
    last = get_column_letter(width)
    row = 1
    label_lengths: dict[int, int] = {}  # etiquetas del bloque de datos, por columna

    def merged(r: int, text, *, first: int = 1, last_col: int = width, font=None, align="left", wrap=False, height=None):
        cell = ws.cell(row=r, column=first, value=text)
        if last_col > first:
            ws.merge_cells(start_row=r, start_column=first, end_row=r, end_column=last_col)
        if font is not None:
            cell.font = font
        cell.alignment = Alignment(horizontal=align, vertical="center", wrap_text=wrap)
        if height:
            ws.row_dimensions[r].height = height
        return cell

    # --- Encabezado del documento -----------------------------------------
    if sheet.get("title"):
        merged(row, str(sheet["title"]), font=Font(bold=True, size=16, color=_DARK), align="center", height=26)
        row += 1
    if sheet.get("subtitle"):
        for line in str(sheet["subtitle"]).splitlines()[:3]:
            merged(row, line.strip(), font=Font(bold=True, size=11), align="center")
            row += 1
    if document and row > 1:
        for col in range(1, width + 1):
            ws.cell(row=row - 1, column=col).border = Border(bottom=medium)
        row += 1

    if info:
        # Dos columnas de pares etiqueta/valor: izquierda y derecha.
        mid = math.ceil(width / 2)
        half = math.ceil(len(info) / 2)
        left, right = info[:half], info[half:]
        for offset in range(half):
            r = row + offset
            for pair, label_col, value_first, value_last in (
                (left[offset] if offset < len(left) else None, 1, 2, mid),
                (right[offset] if offset < len(right) else None, mid + 1, mid + 2, width),
            ):
                if pair is None:
                    continue
                label = str(pair["label"]).strip().rstrip(":") + ":"
                ws.cell(row=r, column=label_col, value=label).font = Font(bold=True)
                label_lengths[label_col] = max(label_lengths.get(label_col, 0), len(label))
                if value_first > width:  # tabla muy angosta: el valor va junto a la etiqueta
                    value_first = value_last = label_col
                    ws.cell(row=r, column=label_col, value=f"{label} {pair.get('value', '')}")
                    continue
                value = str(pair.get("value", ""))
                merged(r, value, first=value_first, last_col=max(value_first, value_last))
                if value_last <= value_first:  # valor en una sola columna: su ancho debe alcanzarle
                    label_lengths[value_first] = max(label_lengths.get(value_first, 0), len(value))
        row += half + 1

    # --- Tabla --------------------------------------------------------------
    if headers:
        for col, text in enumerate(headers, start=1):
            cell = ws.cell(row=row, column=col, value=text)
            cell.font, cell.fill, cell.border = header_font, header_fill, grid
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws.row_dimensions[row].height = 20
        row += 1
    first_data = row
    for i, values in enumerate(rows):
        for col in range(1, table_width + 1):
            fmt = formats[col - 1]
            raw = values[col - 1] if col - 1 < len(values) else None
            cell = ws.cell(row=row, column=col, value=_cell(raw, fmt))
            cell.border = grid if document or headers else Border()
            number_format = _number_format(fmt, symbol)
            if number_format and isinstance(cell.value, (int, float)):
                cell.number_format = number_format
            if fmt in ("integer", "number", "currency", "percent"):
                cell.alignment = Alignment(horizontal="right")
            if document and i % 2 == 1:
                cell.fill = stripe_fill
        row += 1
    last_data = row - 1

    if not document:
        if headers:
            ws.freeze_panes = "A2"
            if rows:
                ws.auto_filter.ref = f"A1:{get_column_letter(table_width)}{last_data}"
    # --- Totales ------------------------------------------------------------
    if totals:
        row += 1
        merged(row, str(sheet.get("totals_title") or "Resumen de impuestos y totales").upper(),
               font=Font(bold=True, size=12, color=_DARK))
        for col in range(1, width + 1):
            ws.cell(row=row, column=col).border = Border(bottom=medium)
        row += 1
        money = _number_format("currency", symbol)
        for item in totals:
            highlight = bool(item.get("highlight"))
            font = Font(bold=True, size=12 if highlight else 11)
            label_last = max(1, width - 2)
            merged(row, str(item["label"]).strip(), last_col=label_last, font=font)
            if item.get("detail") not in (None, ""):
                detail = ws.cell(row=row, column=width - 1, value=_cell(item["detail"]))
                detail.alignment = Alignment(horizontal="right")
                if isinstance(detail.value, float):
                    detail.number_format = "#,##0.00"
            column = item.get("sum_of_column")
            if isinstance(column, int) and 1 <= column <= table_width and last_data >= first_data:
                letter = get_column_letter(column)
                value = f"=SUM({letter}{first_data}:{letter}{last_data})"
            else:
                value = _cell(item.get("value"), "auto")
            cell = ws.cell(row=row, column=width, value=value)
            cell.font = font
            cell.alignment = Alignment(horizontal="right")
            if isinstance(value, (int, float)) or (isinstance(value, str) and value.startswith("=")):
                cell.number_format = money
            if highlight:
                for col in range(1, width + 1):
                    target = ws.cell(row=row, column=col)
                    target.fill = highlight_fill
                    target.border = Border(top=thin, bottom=thin)
                ws.row_dimensions[row].height = 20
            row += 1

    # --- Anchos (antes de las notas: su alto depende del ancho total) --------
    for col in range(1, width + 1):
        letter = get_column_letter(col)
        fmt = formats[col - 1] if col - 1 < len(formats) else "auto"
        lengths = [len(headers[col - 1]) if col - 1 < len(headers) else 0]
        lengths += [_shown_length(ws.cell(row=r, column=col).value, fmt) for r in range(first_data, last_data + 1)]
        lengths.append(label_lengths.get(col, 0))  # las etiquetas no se combinan: también cuentan
        if totals and col == width:
            lengths += [_shown_length(t.get("value"), "currency") for t in totals if isinstance(t.get("value"), (int, float))]
        ws.column_dimensions[letter].width = min(60, max(9, max(lengths) + 3))

    # --- Notas, pie e impresión --------------------------------------------------------
    if notes:
        row += 1
        ws.cell(row=row, column=1, value="Notas:").font = Font(bold=True)
        row += 1
        approx_chars = max(40, int(sum((ws.column_dimensions[get_column_letter(c)].width or 12) for c in range(1, width + 1))))
        for note in notes:
            lines = max(1, math.ceil(len(note) / approx_chars))
            merged(row, f"• {note}", font=Font(italic=True, size=9, color="404040"), wrap=True, height=13 * lines + 2)
            row += 1
    if document:
        row += 1
        merged(row, f"Generado por ATLAS — {datetime.now():%d/%m/%Y %H:%M}",
               font=Font(italic=True, size=8, color=_GREY), align="center")

    if document:
        ws.sheet_view.showGridLines = False
        ws.page_setup.orientation = "portrait"
        ws.page_setup.fitToWidth = 1
        ws.page_setup.fitToHeight = 0
        ws.sheet_properties.pageSetUpPr.fitToPage = True
        ws.print_area = f"A1:{last}{row}"
        ws.print_options.horizontalCentered = True
