from __future__ import annotations

from collections.abc import Sequence

import pandas as pd


COLUNA_SALDO_ACUMULADO_MES = "Saldo Acumulado Atualizado do Mês"


def calcular_saldo_acumulado_mes(
    df: pd.DataFrame,
    col_saldo_dia: str,
    col_dias_abate: str,
    col_agrupamento: str | Sequence[str],
) -> pd.Series:
    """
    Calcula o saldo acumulado mensal por grupo.

    Regra:
    Saldo Acumulado Atualizado do Mês =
    (Saldo Acumulado do Dia * Dias de Abate) + Saldo Acumulado do Mês Anterior

    O DataFrame deve chegar ordenado na sequência temporal desejada dentro de
    cada agrupamento, pois o mês anterior é obtido com groupby().shift(1).
    """
    colunas_agrupamento = [col_agrupamento] if isinstance(col_agrupamento, str) else list(col_agrupamento)
    if not colunas_agrupamento:
        raise ValueError("Informe pelo menos uma coluna de agrupamento para calcular o saldo acumulado.")

    colunas_obrigatorias = pd.Index([col_saldo_dia, col_dias_abate, *colunas_agrupamento])
    colunas_ausentes = colunas_obrigatorias.difference(df.columns)
    if not colunas_ausentes.empty:
        raise KeyError(f"Colunas ausentes para calcular saldo acumulado: {', '.join(colunas_ausentes)}")

    if df.empty:
        return pd.Series(index=df.index, dtype="float64", name=COLUNA_SALDO_ACUMULADO_MES)

    trabalho = df.loc[:, colunas_agrupamento].copy()
    saldo_dia = pd.to_numeric(df[col_saldo_dia], errors="coerce").fillna(0.0)
    dias_abate = pd.to_numeric(df[col_dias_abate], errors="coerce").fillna(0.0)

    trabalho["_saldo_mes_base"] = saldo_dia * dias_abate
    trabalho["_saldo_acumulado"] = trabalho.groupby(
        colunas_agrupamento,
        sort=False,
        dropna=False,
    )["_saldo_mes_base"].cumsum()
    saldo_mes_anterior = trabalho.groupby(
        colunas_agrupamento,
        sort=False,
        dropna=False,
    )["_saldo_acumulado"].shift(1).fillna(0.0)

    saldo_acumulado = trabalho["_saldo_mes_base"] + saldo_mes_anterior
    saldo_acumulado.name = COLUNA_SALDO_ACUMULADO_MES
    return saldo_acumulado
