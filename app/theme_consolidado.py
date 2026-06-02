from __future__ import annotations

from typing import Any

import pandas as pd

from theme_config import COLORS, normalize_label


CONSOLIDADO_COLORS = {
    "gold": COLORS["light_brown"],
    "subtotal_gray": "#757575",
    "total_green": COLORS["green_petroleum"],
    "white": COLORS["white"],
    "near_black": COLORS["near_black"],
    "light_gray": "#E7E7E7",
    "medium_gray": COLORS["medium_gray"],
    "negative": "#0E1421",
    "transparent": COLORS["transparent"],
}

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
    "total kg/dia dispon abate",
    "saldo po atual. x disponivel",
    "saldo po atual x disponivel",
}

FINAL_TOTAL_ROW_LABELS = {
    "saldo po atualizado",
    "saldo acm atualizado / mes",
    "saldo acm atualizado/mes",
    "saldo acm atualizado mes",
}

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
    return _normalized_index_label(row.name)


def _is_section_header(label: str) -> bool:
    return label in SECTION_HEADER_LABELS or label.startswith("quadro")


def _is_subtotal(label: str) -> bool:
    return label in SUBTOTAL_ROW_LABELS or label.startswith("total kg/dia dispon abate")


def _is_final_total(label: str) -> bool:
    return label in FINAL_TOTAL_ROW_LABELS


def _is_gold_row(label: str) -> bool:
    return label in GOLD_ROW_LABELS


def _row_background_style(
    row: pd.Series,
    *,
    label_column: str | None,
    zebra_position: int,
) -> str:
    label = _row_label(row, label_column)

    if not label:
        return _css(CONSOLIDADO_COLORS["transparent"], CONSOLIDADO_COLORS["near_black"])

    if _is_section_header(label):
        return _css(
            CONSOLIDADO_COLORS["gold"],
            CONSOLIDADO_COLORS["white"],
            font_weight="900",
            text_align="left",
        )

    if _is_gold_row(label):
        return _css(CONSOLIDADO_COLORS["gold"], CONSOLIDADO_COLORS["white"], font_weight="800")

    if _is_subtotal(label):
        return _css(CONSOLIDADO_COLORS["subtotal_gray"], CONSOLIDADO_COLORS["white"], font_weight="900")

    if _is_final_total(label):
        return _css(CONSOLIDADO_COLORS["total_green"], CONSOLIDADO_COLORS["white"], font_weight="900")

    if zebra_position % 2 == 0:
        return _css(CONSOLIDADO_COLORS["white"], CONSOLIDADO_COLORS["near_black"])
    return _css(CONSOLIDADO_COLORS["light_gray"], CONSOLIDADO_COLORS["near_black"])


def _is_negative(value: Any) -> bool:
    numeric_value = pd.to_numeric(value, errors="coerce")
    return pd.notna(numeric_value) and numeric_value < 0


def style_negative_values(value: Any) -> str:
    """Pinta valores numericos negativos de vermelho, preservando o fundo da linha."""
    if _is_negative(value):
        return f"color: {CONSOLIDADO_COLORS['negative']};"
    return ""


def _apply_negative_styles(styler: pd.io.formats.style.Styler) -> pd.io.formats.style.Styler:
    if hasattr(styler, "map"):
        return styler.map(style_negative_values)
    return styler.applymap(style_negative_values)


def style_consolidado_dataframe(
    df: pd.DataFrame,
    *,
    label_column: str | None = None,
    hide_index: bool = True,
) -> pd.io.formats.style.Styler:
    """Aplica o tema da tela Consolidado (APT + ITA) em um DataFrame.

    A cor de negativos e aplicada depois do estilo das linhas para sobrescrever
    a cor de texto definida por totais, subtotais ou zebrado.
    """
    resolved_label_column = _resolve_label_column(df, label_column)
    zebra_positions: dict[Any, int] = {}
    zebra_count = 0

    for index, row in df.iterrows():
        label = _row_label(row, resolved_label_column)
        if _is_section_header(label) or _is_gold_row(label) or _is_subtotal(label) or _is_final_total(label):
            continue
        zebra_positions[index] = zebra_count
        zebra_count += 1

    def apply_row_style(row: pd.Series) -> list[str]:
        style = _row_background_style(
            row,
            label_column=resolved_label_column,
            zebra_position=zebra_positions.get(row.name, 0),
        )
        return [style] * len(row)

    styler = (
        _apply_negative_styles(df.style.apply(apply_row_style, axis=1))
        .set_table_styles(
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
                        ("background-color", CONSOLIDADO_COLORS["gold"]),
                        ("color", CONSOLIDADO_COLORS["white"]),
                        ("font-weight", "900"),
                        ("text-align", "center"),
                        ("border", f"1px solid {CONSOLIDADO_COLORS['medium_gray']}"),
                    ],
                },
                {
                    "selector": "td",
                    "props": [
                        ("border", f"1px solid {CONSOLIDADO_COLORS['medium_gray']}"),
                        ("text-align", "center"),
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
