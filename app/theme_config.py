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
    # "medium_gray": "#757575",
    "medium_gray": "#CFCFCF",
    "dark_gray": "#757171",
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


def style_negative_value(value: Any) -> str:
    numeric_value = _coerce_display_number(value)
    if numeric_value is not None and numeric_value < 0:
        return "font-size: 1.10em;"
    return ""


def _apply_negative_value_styles(
    styler: pd.io.formats.style.Styler,
    subset: list[str] | None = None,
) -> pd.io.formats.style.Styler:
    if hasattr(styler, "map"):
        return styler.map(style_negative_value, subset=subset)
    return styler.applymap(style_negative_value, subset=subset)


def _section_pattern(label: str) -> PatternName | None:
    if label.startswith("quadro de peixe gordo - proprio"):
        return "A"
    if label.startswith("quadro de peixe gordo - integracao"):
        return "B"
    if label.startswith("quadro de peixe gordo - parceria"):
        return "C"
    if label.startswith("quadro de peixe gordo total"):
        return "A"
    if label.startswith("quadro de disponibilidade"):
        return "B"
    if label.startswith("quadro do saldo"):
        return "C"
    return None


def _is_section_header(label: str) -> bool:
    return label.startswith("quadro")


def _is_section_footer(label: str) -> bool:
    return (
        label.startswith("total ")
        or label.startswith("abate po atualizado total")
        or label.startswith("total kg/dia")
        or label.startswith("saldo acm atualizado")
    )


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

        body_row_count += 1
        if body_row_count % 2 == 1:
            styles[index] = _css(current_pattern.odd_background, current_pattern.odd_text)
        else:
            styles[index] = _css(current_pattern.even_background, current_pattern.even_text)

    return styles


def style_dark_regional_report(
    df: pd.DataFrame,
    *,
    label_column: str = "Conteúdo / Bloco",
    default_pattern: PatternName | None = None,
) -> pd.io.formats.style.Styler:
    label_column = _resolve_label_column(df, label_column)
    row_styles = _row_styles(df, label_column, default_pattern)

    def apply_row_style(row: pd.Series) -> list[str]:
        style = row_styles.get(row.name, _css(COLORS["transparent"], COLORS["plot_header_text"]))
        return [style] * len(row)

    value_columns = [column for column in df.columns if column != label_column]
    formatters = {column: format_negative_value for column in value_columns}
    styler = _apply_negative_value_styles(
        df.style.apply(apply_row_style, axis=1).format(formatters),
        subset=value_columns,
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
                        ("text-align", "center"),
                        ("border-bottom", f"1px solid {COLORS['medium_gray']}"),
                    ],
                },
                {
                    "selector": "td",
                    "props": [
                        ("border-color", COLORS["medium_gray"]),
                        ("text-align", "center"),
                    ],
                },
            ]
        )
        .hide(axis="index")
    )

    return styler
