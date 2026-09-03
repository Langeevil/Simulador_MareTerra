from __future__ import annotations

from typing import Any

import pandas as pd

from theme_config import COLORS, TABLE_PATTERNS, format_negative_value, normalize_label, style_numeric_value


CONSOLIDADO_COLORS = {
    "white": COLORS["white"],
    "near_black": COLORS["near_black"],
    "medium_gray": COLORS["medium_gray"],
    "highlight_gray": "#757575",
    "transparent": COLORS["transparent"],
}

PATTERN_SEQUENCE = ("A", "B", "C")

SECTION_HEADER_LABELS = {
    "apt",
    "ita",
    "itapora",
    "consolidado",
    "consolidado apt + ita",
}

GOLD_ROW_LABELS = {
    "dias de abate",
}

SUBTOTAL_ROW_LABELS = {
    "saldo po atual x disponivel",
}

FINAL_TOTAL_ROW_LABELS = {
    "saldo po",
    "saldo acm atualizado / mes",
    "saldo acm atualizado/mes",
    "saldo acm atualizado mes",
    "peso medio",
}

ZEBRA_ROW_LABELS = {
    "saldo po atualizado",
    "saldo po",
}

HIGHLIGHT_ROW_MARKERS = (
    "saldo po",
    "total",
    "peso medio",
)

LABEL_COLUMN_CANDIDATES = (
    "Conteudo / Bloco",
    "Bloco",
    "Indicador",
    "Descricao",
)


def _css(
    background: str,
    color: str,
    *,
    font_weight: str = "500",
    text_align: str | None = None,
) -> str:
    props = [
        f"background-color: {background}",
        f"color: {color}",
        f"font-weight: {font_weight}",
    ]
    if text_align:
        props.append(f"text-align: {text_align}")
    return "; ".join(props) + ";"


def _normalized_index_label(index_value: Any) -> str:
    if isinstance(index_value, tuple):
        return normalize_label(" ".join(str(value) for value in index_value))
    return normalize_label(index_value)


def _resolve_label_column(df: pd.DataFrame, label_column: str | None) -> str | None:
    if label_column and label_column in df.columns:
        return label_column

    if label_column:
        target = normalize_label(label_column)
        for column in df.columns:
            if normalize_label(column) == target:
                return str(column)

    for candidate in LABEL_COLUMN_CANDIDATES:
        target = normalize_label(candidate)
        for column in df.columns:
            if normalize_label(column) == target:
                return str(column)

    return str(df.columns[0]) if len(df.columns) else None


def _row_label(row: pd.Series, label_column: str | None) -> str:
    if label_column and label_column in row.index:
        value = row.get(label_column)
        if pd.notna(value) and str(value).strip():
            return normalize_label(value)
        return ""
    return _normalized_index_label(row.name)


def _first_column_label(row: pd.Series) -> str:
    if row.empty:
        return ""
    value = row.iloc[0]
    if pd.isna(value) or not str(value).strip():
        return ""
    return normalize_label(value)


def _is_gray_highlight_row(row: pd.Series) -> bool:
    search_text = f"{_normalized_index_label(row.name)} {_first_column_label(row)}"
    return any(marker in search_text for marker in HIGHLIGHT_ROW_MARKERS)


def _is_section_header(label: str) -> bool:
    return label in SECTION_HEADER_LABELS or label.startswith("qd")


def _is_subtotal(label: str) -> bool:
    return label in SUBTOTAL_ROW_LABELS 
# or label.startswith("total kg/dia dispon abate")


def _is_final_total(label: str) -> bool:
    if label in ZEBRA_ROW_LABELS:
        return False
    return label in FINAL_TOTAL_ROW_LABELS


def _is_gold_row(label: str) -> bool:
    return label in GOLD_ROW_LABELS


def _table_pattern(section_index: int):
    pattern_name = PATTERN_SEQUENCE[section_index % len(PATTERN_SEQUENCE)]
    return TABLE_PATTERNS[pattern_name]


def _last_table_row_indices(df: pd.DataFrame, label_column: str | None) -> set[Any]:
    last_indices: set[Any] = set()
    current_last_index: Any | None = None

    for index, row in df.iterrows():
        label = _row_label(row, label_column)

        if not label:
            if current_last_index is not None:
                last_indices.add(current_last_index)
            current_last_index = None
            continue

        if _is_section_header(label):
            if current_last_index is not None:
                last_indices.add(current_last_index)
            current_last_index = None
            continue

        current_last_index = index

    if current_last_index is not None:
        last_indices.add(current_last_index)

    return last_indices


def _row_styles(df: pd.DataFrame, label_column: str | None) -> dict[Any, str]:
    styles: dict[Any, str] = {}
    current_pattern = None
    section_count = 0
    body_row_count = 0
    last_table_rows = _last_table_row_indices(df, label_column)

    for index, row in df.iterrows():
        label = _row_label(row, label_column)
        is_gray_highlight = (
            _is_gray_highlight_row(row)
            and label not in ZEBRA_ROW_LABELS
            and index not in last_table_rows
        )

        if not label:
            if is_gray_highlight:
                styles[index] = _css(
                    CONSOLIDADO_COLORS["highlight_gray"],
                    CONSOLIDADO_COLORS["white"],
                    font_weight="900",
                )
            else:
                styles[index] = _css(CONSOLIDADO_COLORS["white"], CONSOLIDADO_COLORS["near_black"])
            current_pattern = None
            body_row_count = 0
            continue

        if _is_section_header(label):
            current_pattern = _table_pattern(section_count)
            section_count += 1
            body_row_count = 0
            styles[index] = _css(
                current_pattern.header_footer_background,
                current_pattern.header_footer_text,
                font_weight="900",
                text_align="left",
            )
            continue

        if is_gray_highlight:
            styles[index] = _css(
                CONSOLIDADO_COLORS["highlight_gray"],
                CONSOLIDADO_COLORS["white"],
                font_weight="900",
            )
            continue

        if current_pattern is None:
            styles[index] = _css(CONSOLIDADO_COLORS["transparent"], CONSOLIDADO_COLORS["near_black"])
            continue

        if index in last_table_rows or _is_gold_row(label) or _is_subtotal(label) or _is_final_total(label):
            styles[index] = _css(
                current_pattern.header_footer_background,
                current_pattern.header_footer_text,
                font_weight="900",
            )
            continue

        body_row_count += 1
        if body_row_count % 2 == 1:
            styles[index] = _css(current_pattern.odd_background, current_pattern.odd_text)
        else:
            styles[index] = _css(current_pattern.even_background, current_pattern.even_text)

    return styles


def _apply_numeric_styles(
    styler: pd.io.formats.style.Styler,
    subset: list[str] | None = None,
) -> pd.io.formats.style.Styler:
    if hasattr(styler, "map"):
        return styler.map(style_numeric_value, subset=subset)
    return styler.applymap(style_numeric_value, subset=subset)


def style_consolidado_dataframe(
    df: pd.DataFrame,
    *,
    label_column: str | None = None,
    hide_index: bool = True,
    df_tooltips: pd.DataFrame | None = None,
) -> pd.io.formats.style.Styler:
    """Aplica o tema da tela Consolidado (APT + ITA) em um DataFrame.

    A cor de negativos e aplicada depois do estilo das linhas para sobrescrever
    a cor de texto definida por totais, subtotais ou zebrado.
    """
    resolved_label_column = _resolve_label_column(df, label_column)
    row_styles = _row_styles(df, resolved_label_column)

    def apply_row_style(row: pd.Series) -> list[str]:
        style = row_styles.get(
            row.name,
            _css(CONSOLIDADO_COLORS["transparent"], CONSOLIDADO_COLORS["near_black"]),
        )
        return [style] * len(row)

    value_columns = [column for column in df.columns if column != resolved_label_column]
    styler = _apply_numeric_styles(df.style.apply(apply_row_style, axis=1), subset=value_columns)
    formatters = {column: format_negative_value for column in value_columns}

    if resolved_label_column:
        formatters[resolved_label_column] = (
            lambda value: ""
            if normalize_label(value) in {"qd", "apt", "ita", "itapora"}
            else value
        )

    styler = styler.format(formatters)
    
    if df_tooltips is not None:
        def apply_tooltip_color(val):
            if pd.notna(val) and val is not None and str(val).strip() != "":
                if "Entrada" in str(val): return "color: #4CAF50; font-weight: 800;"
                if "Saída" in str(val): return "color: #F44336; font-weight: 800;"
            return ""
            
        if hasattr(df_tooltips, "applymap"):
            styler = styler.apply(
                lambda df_vals: df_tooltips.applymap(apply_tooltip_color),
                axis=None
            )
        else:
            styler = styler.apply(
                lambda df_vals: df_tooltips.map(apply_tooltip_color),
                axis=None
            )

    styler = (
        styler.set_table_styles(
            [
                {
                    "selector": "table",
                    "props": [
                        ("border-collapse", "collapse"),
                        ("background-color", CONSOLIDADO_COLORS["white"]),
                    ],
                },
                {
                    "selector": "th",
                    "props": [
                        ("background-color", COLORS["transparent"]),
                        ("color", COLORS["plot_header_text"]),
                        ("font-weight", "900"),
                        ("text-align", "left"),
                        ("border", f"1px solid {CONSOLIDADO_COLORS['medium_gray']}"),
                    ],
                },
                {
                    "selector": "td",
                    "props": [
                        ("border", f"1px solid {CONSOLIDADO_COLORS['medium_gray']}"),
                    ],
                },
            ]
        )
    )

    if resolved_label_column:
        styler = styler.set_properties(
            subset=[resolved_label_column],
            **{
                "text-align": "left",
                "min-width": "280px",
                "white-space": "normal",
                "word-wrap": "break-word",
                "font-weight": "700",
            },
        )

    if hide_index:
        styler = styler.hide(axis="index")

    return styler


def aplicar_tema_consolidado(
    df: pd.DataFrame,
    *,
    label_column: str | None = None,
    hide_index: bool = True,
) -> pd.io.formats.style.Styler:
    """Alias em portugues para uso direto na tela Consolidado."""
    return style_consolidado_dataframe(df, label_column=label_column, hide_index=hide_index)
