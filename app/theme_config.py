from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Literal

import pandas as pd


ColorName = Literal[
    "transparent",
    "plot_header_text",
    "green_petroleum",
    "light_brown",
    "medium_gray",
    "dark_gray",
    "white",
    "near_black",
    "brown",
]
PatternName = Literal["A", "B", "C"]


COLORS: dict[ColorName, str] = {
    "transparent": "transparent",
    "plot_header_text": "#a5a7a7",
    "green_petroleum": "#17413B",
    "light_brown": "#bc933f",
    # "medium_gray": "#a6a6a6",
    # "medium_gray": "#757171",
    "medium_gray": "#CFCFCF",
    "dark_gray": "#757575",
    "white": "#FFFFFF",
    "near_black": "#111827",
    # "brown": "#FBBF24",
    "brown": "#111827",
}

NEGATIVE_PREFIX = "\U0001F53B "


@dataclass(frozen=True)
class TablePattern:
    name: PatternName
    header_footer_background: str
    header_footer_text: str
    odd_background: str
    odd_text: str
    even_background: str
    even_text: str


TABLE_PATTERNS: dict[PatternName, TablePattern] = {
    "A": TablePattern(
        name="A",
        header_footer_background=COLORS["green_petroleum"],
        header_footer_text=COLORS["white"],
        odd_background=COLORS["white"],
        odd_text=COLORS["near_black"],
        even_background=COLORS["medium_gray"],
        even_text=COLORS["near_black"],
    ),
    "B": TablePattern(
        name="B",
        header_footer_background=COLORS["light_brown"],
        header_footer_text=COLORS["white"],
        odd_background=COLORS["white"],
        odd_text=COLORS["near_black"],
        even_background=COLORS["medium_gray"],
        even_text=COLORS["brown"],
    ),
    "C": TablePattern(
        name="C",
        header_footer_background=COLORS["dark_gray"],
        header_footer_text=COLORS["white"],
        odd_background=COLORS["white"],
        odd_text=COLORS["near_black"],
        even_background=COLORS["medium_gray"],
        even_text=COLORS["brown"],
    ),
}


def _repair_mojibake(text: str) -> str:
    """Best-effort repair for strings that were decoded as Latin-1 before UTF-8."""
    if "Ã" not in text and "Â" not in text:
        return text
    try:
        return text.encode("latin1").decode("utf-8")
    except UnicodeError:
        return text


def normalize_label(value: Any) -> str:
    text = _repair_mojibake(str(value or ""))
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"\s+", " ", text).strip().lower()
    return text


def _css(
    background: str,
    color: str,
    *,
    font_weight: str = "600",
    border_top: str | None = None,
    border_bottom: str | None = None,
) -> str:
    declarations = [
        f"background-color: {background}",
        f"color: {color}",
        f"font-weight: {font_weight}",
    ]
    if border_top:
        declarations.append(f"border-top: {border_top}")
    if border_bottom:
        declarations.append(f"border-bottom: {border_bottom}")
    return "; ".join(declarations) + ";"


def _coerce_display_number(value: Any) -> float | None:
    if pd.isna(value) or value == "":
        return None

    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        has_negative_prefix = text.startswith(NEGATIVE_PREFIX)
        text = text.removeprefix(NEGATIVE_PREFIX).strip()
        text = text.replace(".", "").replace(",", ".")
        try:
            numeric_value = float(text)
        except ValueError:
            return None
        return -abs(numeric_value) if has_negative_prefix else numeric_value

    numeric_value = pd.to_numeric(value, errors="coerce")
    if pd.isna(numeric_value):
        return None
    return float(numeric_value)


def is_display_numeric_value(value: Any) -> bool:
    return _coerce_display_number(value) is not None


def _display_number_preserving_sign(value: Any) -> str:
    if isinstance(value, str):
        text = value.strip().removeprefix(NEGATIVE_PREFIX).strip()
        return text

    numeric_value = float(value)
    if numeric_value.is_integer():
        return f"{numeric_value:,.0f}".replace(",", ".")
    return f"{numeric_value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def format_negative_value(value: Any) -> Any:
    if isinstance(value, str) and value.strip().startswith(NEGATIVE_PREFIX):
        return value

    numeric_value = _coerce_display_number(value)
    if numeric_value is not None and numeric_value < 0:
        return f"{NEGATIVE_PREFIX}{_display_number_preserving_sign(value)}"
    return value

def format_transfer_value(value: Any) -> Any:
    numeric_value = _coerce_display_number(value)
    if numeric_value is None:
        return value
        
    if numeric_value < 0:
        return f"📉 {_display_number_preserving_sign(value)}"
    elif numeric_value > 0:
        return f"📈 {_display_number_preserving_sign(value)}"
    else:
        return f"{_display_number_preserving_sign(value)}"


def style_numeric_value(value: Any) -> str:
    numeric_value = _coerce_display_number(value)
    if numeric_value is None:
        return ""

    declarations = ["text-align: center"]
    if numeric_value < 0:
        declarations.append("font-size: 1.10em")
    return "; ".join(declarations) + ";"


def _apply_numeric_value_styles(
    styler: pd.io.formats.style.Styler,
    subset: list[str] | None = None,
) -> pd.io.formats.style.Styler:
    if hasattr(styler, "map"):
        return styler.map(style_numeric_value, subset=subset)
    return styler.applymap(style_numeric_value, subset=subset)


def _section_pattern(label: str) -> PatternName | None:
    if label.startswith("qd peixe gordo - proprio"):
        return "A"
    if label.startswith("qd peixe gordo - integracao"):
        return "B"
    if label.startswith("qd peixe gordo - parceria"):
        return "C"
    if label.startswith("qd peixe gordo total"):
        return "A"
    if label.startswith("qd disp"):
        return "B"
    if label.startswith("qd saldo"):
        return "C"
    return None


def _is_section_header(label: str) -> bool:
    return label.startswith("qd")


def _is_section_footer(label: str) -> bool:
    return (
        label.startswith("total ")
        or label.startswith("abate po atualizado total")
        or label.startswith("total kg/dia")
        or label.startswith("saldo acm atualizado")
    )


def _is_dark_gray_row(label: str) -> bool:
    return label in {
        "previsao disponibilidade total",
        "previsao de disponibilidade total",
    }


def _resolve_label_column(df: pd.DataFrame, label_column: str) -> str:
    if label_column in df.columns:
        return label_column

    normalized_target = normalize_label(label_column)
    for column in df.columns:
        if normalize_label(column) == normalized_target:
            return str(column)

    raise ValueError(f"Coluna obrigatoria ausente no relatorio: {label_column}")


def _row_styles(
    df: pd.DataFrame,
    label_column: str,
    default_pattern: PatternName | None = None,
) -> dict[Any, str]:
    styles: dict[Any, str] = {}
    current_pattern: TablePattern | None = TABLE_PATTERNS[default_pattern] if default_pattern else None
    body_row_count = 0

    for index, row in df.iterrows():
        label = normalize_label(row.get(label_column, ""))

        if not label:
            styles[index] = _css(COLORS["transparent"], COLORS["plot_header_text"])
            current_pattern = None
            body_row_count = 0
            continue

        next_pattern = _section_pattern(label)
        if next_pattern is not None:
            current_pattern = TABLE_PATTERNS[next_pattern]
            body_row_count = 0

        if current_pattern is None:
            styles[index] = _css(COLORS["transparent"], COLORS["plot_header_text"])
            continue

        if _is_section_header(label):
            styles[index] = _css(
                current_pattern.header_footer_background,
                current_pattern.header_footer_text,
                font_weight="900",
                border_top=f"1px solid {current_pattern.header_footer_background}",
                border_bottom=f"1px solid {current_pattern.header_footer_background}",
            )
            continue

        if _is_section_footer(label):
            styles[index] = _css(
                current_pattern.header_footer_background,
                current_pattern.header_footer_text,
                font_weight="900",
                border_top=f"1px solid {current_pattern.header_footer_background}",
                border_bottom=f"1px solid {current_pattern.header_footer_background}",
            )
            continue

        if _is_dark_gray_row(label):
            styles[index] = _css(
                COLORS["dark_gray"],
                COLORS["white"],
                font_weight="900",
                border_top=f"1px solid {COLORS['dark_gray']}",
                border_bottom=f"1px solid {COLORS['dark_gray']}",
            )
            continue

        body_row_count += 1
        if body_row_count % 2 == 1:
            styles[index] = _css(current_pattern.odd_background, current_pattern.odd_text)
        else:
            styles[index] = _css(current_pattern.even_background, current_pattern.even_text)

    return styles


def style_sobras_faltas_dataframe(
    df: pd.DataFrame,
    pattern_name: PatternName = "A",
) -> pd.io.formats.style.Styler:
    """Aplica o tema padrão Mar & Terra na tabela de Sobras x Faltas."""
    pattern = TABLE_PATTERNS[pattern_name]
    
    def _row_styles(row):
        row_idx = df.index.get_loc(row.name)
        if row_idx % 2 == 0:
            bg = pattern.even_background
            text = pattern.even_text
        else:
            bg = pattern.odd_background
            text = pattern.odd_text
        return [_css(bg, text) for _ in row]

    styler = df.style.apply(_row_styles, axis=1)

    def color_falta(val, row_idx):
        numeric_val = _coerce_display_number(val)
        bg = pattern.even_background if row_idx % 2 == 0 else pattern.odd_background
        if numeric_val and numeric_val > 0:
            return f"color: #EF4444; font-weight: bold; background-color: {bg}"
        text = pattern.even_text if row_idx % 2 == 0 else pattern.odd_text
        return f"color: {text}; background-color: {bg}"

    def color_sobra(val, row_idx):
        numeric_val = _coerce_display_number(val)
        bg = pattern.even_background if row_idx % 2 == 0 else pattern.odd_background
        if numeric_val and numeric_val > 0:
            return f"color: #0077B6; font-weight: bold; background-color: {bg}"
        text = pattern.even_text if row_idx % 2 == 0 else pattern.odd_text
        return f"color: {text}; background-color: {bg}"

    # Apply conditional colors using row index
    for row_idx in range(len(df)):
        if "Biomassa que faltou para a Meta" in df.columns:
            styler = styler.map(lambda val, idx=row_idx: color_falta(val, idx), subset=pd.IndexSlice[df.index[row_idx], ["Biomassa que faltou para a Meta"]])
        if "Sobra de Biomassa Pronta" in df.columns:
            styler = styler.map(lambda val, idx=row_idx: color_sobra(val, idx), subset=pd.IndexSlice[df.index[row_idx], ["Sobra de Biomassa Pronta"]])

    def format_to_tonnes(value: Any) -> str:
        if isinstance(value, str):
            try:
                numeric_val = float(value.replace(",", "."))
            except ValueError:
                return value
        else:
            try:
                numeric_val = float(value)
            except (TypeError, ValueError):
                return str(value)
        
        tonnes = numeric_val / 1000.0
        return f"{tonnes:,.1f} t".replace(",", "X").replace(".", ",").replace("X", ".")

    styler = _apply_numeric_value_styles(styler)
    
    # Identify which columns to convert to tonnes (all numeric ones except Mês, Produtor, Tanque, etc)
    non_metric_cols = {"Mês", "Produtor", "Produtor de Origem", "Tanque", "Produtor de Destino"}
    metric_cols = [c for c in df.columns if c not in non_metric_cols]
    
    if metric_cols:
        styler = styler.format(format_to_tonnes, subset=metric_cols)
    else:
        styler = styler.format(_display_number_preserving_sign)

    # Highlight interactive columns headers
    interactive_cols = [
        "Disponível", 
        "Alocação Própria", 
        "Alocação p/ Terceiros", 
        "Alocação Total", 
        "Sobra de Biomassa Pronta"
    ]
    interactive_styles = {
        col: [{'selector': 'th', 'props': [('background-color', '#FEF08A'), ('color', '#000000')]}]
        for col in interactive_cols if col in df.columns
    }
    if interactive_styles:
        styler.set_table_styles(interactive_styles, overwrite=False)

    styler = styler.set_table_styles(
        [
            {
                "selector": "thead th",
                "props": [
                    ("background-color", pattern.header_footer_background),
                    ("color", pattern.header_footer_text),
                    ("font-weight", "800"),
                    ("text-align", "center"),
                    ("border-bottom", f"1px solid {COLORS['medium_gray']}"),
                ],
            },
            {
                "selector": "td",
                "props": [
                    ("border-color", COLORS["medium_gray"]),
                ],
            },
        ]
    ).hide(axis="index")
    
    return styler


def style_dark_regional_report(
    df: pd.DataFrame,
    *,
    label_column: str = "Conteúdo / Bloco",
    default_pattern: PatternName | None = None,
    df_tooltips: pd.DataFrame | None = None,
) -> pd.io.formats.style.Styler:
    label_column = _resolve_label_column(df, label_column)
    row_styles = _row_styles(df, label_column, default_pattern)

    def apply_row_style(row: pd.Series) -> list[str]:
        style = row_styles.get(row.name, _css(COLORS["transparent"], COLORS["plot_header_text"]))
        return [style] * len(row)

    value_columns = [column for column in df.columns if column != label_column]
    formatters = {column: format_negative_value for column in value_columns}
    styler = _apply_numeric_value_styles(
        df.style.apply(apply_row_style, axis=1).format(formatters),
        subset=value_columns,
    )

    if df_tooltips is not None:
        def apply_tooltip_color(val):
            if pd.notna(val) and val is not None and str(val).strip() != "":
                if "Entrada" in str(val): return "color: #4CAF50; font-weight: 800;"
                if "Saída" in str(val): return "color: #F44336; font-weight: 800;"
            return ""
            
        if hasattr(df_tooltips, "map"):
            styler = styler.apply(
                lambda df_vals: df_tooltips.map(apply_tooltip_color),
                axis=None
            )
        else:
            styler = styler.apply(
                lambda df_vals: df_tooltips.applymap(apply_tooltip_color),
                axis=None
            )

    styler = (
        styler
        .set_properties(
            subset=[label_column],
            **{
                "min-width": "350px",
                "max-width": "450px",
                "white-space": "normal",
                "word-wrap": "break-word",
                "font-weight": "700",
                "text-align": "left",
            },
        )
        .set_table_styles(
            [
                {
                    "selector": "table",
                    "props": [
                        ("background-color", COLORS["transparent"]),
                    ],
                },
                {
                    "selector": "th",
                    "props": [
                        ("background-color", COLORS["transparent"]),
                        ("color", COLORS["plot_header_text"]),
                        ("font-weight", "800"),
                        ("text-align", "left"),
                        ("border-bottom", f"1px solid {COLORS['medium_gray']}"),
                    ],
                },
                {
                    "selector": "td",
                    "props": [
                        ("border-color", COLORS["medium_gray"]),
                    ],
                },
            ]
        )
        .hide(axis="index")
    )

    return styler
