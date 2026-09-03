from __future__ import annotations

import pandas as pd
from typing import Literal
from theme_config import COLORS, TABLE_PATTERNS, format_negative_value, normalize_label, PatternName

def _css(background: str, color: str, *, font_weight: str = "500", text_align: str | None = None) -> str:
    props = [
        f"background-color: {background}",
        f"color: {color}",
        f"font-weight: {font_weight}",
    ]
    if text_align:
        props.append(f"text-align: {text_align}")
    return "; ".join(props) + ";"

def format_value(val, is_percentage: bool = False):
    if pd.isna(val) or val == "":
        return ""
    try:
        val = float(val)
        if is_percentage:
            return f"{val * 100:,.2f}%".replace(",", "X").replace(".", ",").replace("X", ".")
        return f"{val:,.0f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (ValueError, TypeError):
        return str(val)

def style_esperado_realizado_dataframe(
    df: pd.DataFrame,
    *,
    hide_index: bool = True,
    pattern_name: PatternName = "A",
) -> pd.io.formats.style.Styler:
    """Aplica o tema da tela Esperado x Realizado, alinhado com theme_consolidado."""
    
    if df.empty:
        return df.style

    label_column = df.columns[0]
    pattern = TABLE_PATTERNS[pattern_name]
    
    def apply_row_style(row: pd.Series) -> list[str]:
        label = normalize_label(str(row.get(label_column, "")))
        
        # Somente a última linha (%) age como footer com a cor principal
        if "porcentagem" in label or "%" in label:
            style = _css(pattern.header_footer_background, pattern.header_footer_text, font_weight="900")
        else:
            # Alterna odd/even para o resto (Realizada e Esperada)
            row_idx = df.index.get_loc(row.name)
            if row_idx % 2 == 0:
                style = _css(pattern.even_background, pattern.even_text)
            else:
                style = _css(pattern.odd_background, pattern.odd_text)
            
        return [style] * len(row)

    value_columns = [col for col in df.columns if col != label_column]
    
    styler = df.style.apply(apply_row_style, axis=1)
    
    # Formatação condicional (ex: porcentagem vs absoluto)
    for row_idx in range(len(df)):
        label = normalize_label(str(df.iloc[row_idx][label_column]))
        is_perc = "porcentagem" in label or "%" in label
        styler = styler.format(
            lambda val, is_p=is_perc: format_value(val, is_percentage=is_p), 
            subset=pd.IndexSlice[row_idx:row_idx, value_columns]
        )

    styler = (
        styler.set_table_styles(
            [
                {
                    "selector": "table",
                    "props": [
                        ("border-collapse", "collapse"),
                        ("background-color", COLORS["white"]),
                    ],
                },
                {
                    "selector": "th",
                    "props": [
                        ("background-color", pattern.header_footer_background),
                        ("color", pattern.header_footer_text),
                        ("font-weight", "900"),
                        ("text-align", "center"),
                        ("border", f"1px solid {COLORS['medium_gray']}"),
                    ],
                },
                {
                    "selector": "td",
                    "props": [
                        ("border", f"1px solid {COLORS['medium_gray']}"),
                        ("text-align", "center"),
                    ],
                },
            ]
        )
    )

    styler = styler.set_properties(
        subset=[label_column],
        **{
            "text-align": "left",
            "min-width": "200px",
            "font-weight": "700",
        },
    )

    if hide_index:
        styler = styler.hide(axis="index")

    return styler
