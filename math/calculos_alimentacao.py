from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime

import numpy as np
import pandas as pd


COLUNA_CONSUMO_RACAO_ACUMULADO = "Consumo de Racao Acumulado (kg)"
COLUNA_CONSUMO_RACAO_NA_FASE = "Consumo de Racao na Fase (kg)"
COLUNA_TCA_DIARIO = "TCA Diario"
COLUNA_TCA_ACUMULADO = "TCA Acumulado"


def _colunas_grupo(col_agrupamento: str | Sequence[str] | None) -> list[str]:
    if col_agrupamento is None:
        return []
    if isinstance(col_agrupamento, str):
        return [col_agrupamento]
    return list(col_agrupamento)


def _validar_colunas(df: pd.DataFrame, colunas: Sequence[str]) -> None:
    ausentes = pd.Index(colunas).difference(df.columns)
    if not ausentes.empty:
        raise KeyError(f"Colunas ausentes: {', '.join(ausentes)}")


def _ordenar_para_calculo(
    df: pd.DataFrame,
    col_agrupamento: str | Sequence[str] | None = None,
    col_data: str | None = None,
) -> pd.DataFrame:
    colunas_ordenacao = [*_colunas_grupo(col_agrupamento)]
    if col_data:
        colunas_ordenacao.append(col_data)
    if not colunas_ordenacao:
        return df.copy()
    _validar_colunas(df, colunas_ordenacao)
    return df.sort_values(colunas_ordenacao, kind="mergesort").copy()


def _serie_filtrada_por_data_base(
    df: pd.DataFrame,
    valores: pd.Series,
    col_data: str | None,
    data_base: date | datetime | str | pd.Timestamp | None,
) -> pd.Series:
    if data_base is None:
        return valores
    if not col_data:
        raise ValueError("Informe col_data quando data_base for usada.")
    _validar_colunas(df, [col_data])

    datas = pd.to_datetime(df[col_data], errors="coerce")
    data_ref = pd.to_datetime(data_base)
    return pd.Series(
        np.where(datas >= data_ref, valores.fillna(0.0), 0.0),
        index=df.index,
        dtype="float64",
    )


def calcular_consumo_racao_acumulado(
    df: pd.DataFrame,
    col_consumo_diario: str,
    col_agrupamento: str | Sequence[str] | None,
    col_data: str | None = None,
    data_base: date | datetime | str | pd.Timestamp | None = None,
) -> pd.Series:
    """
    Calcula o consumo acumulado por lote com cumsum vetorizado.

    Quando `data_base` for informada, linhas anteriores a ela entram no cumsum
    como zero. Isso copia a regra de antecedencia usada no acumulado do
    simulador para permitir uma troca paralela no futuro.
    """
    colunas = [col_consumo_diario, *_colunas_grupo(col_agrupamento)]
    if col_data:
        colunas.append(col_data)
    _validar_colunas(df, colunas)

    trabalho = _ordenar_para_calculo(df, col_agrupamento, col_data)
    consumo_diario = pd.to_numeric(trabalho[col_consumo_diario], errors="coerce").fillna(0.0)
    consumo_para_acumulo = _serie_filtrada_por_data_base(
        trabalho,
        consumo_diario,
        col_data=col_data,
        data_base=data_base,
    )

    grupos = _colunas_grupo(col_agrupamento)
    if grupos:
        acumulado = consumo_para_acumulo.groupby(
            [trabalho[col] for col in grupos],
            sort=False,
            dropna=False,
        ).cumsum()
    else:
        acumulado = consumo_para_acumulo.cumsum()

    acumulado = acumulado.reindex(df.index)
    acumulado.name = COLUNA_CONSUMO_RACAO_ACUMULADO
    return acumulado


def calcular_consumo_racao_acumulado_por_fase(
    df: pd.DataFrame,
    col_consumo_diario: str,
    col_fase: str,
    col_agrupamento: str | Sequence[str] | None,
    col_data: str | None = None,
) -> pd.Series:
    """
    Calcula o consumo acumulado dentro da fase nutricional ativa.
    """
    grupos = [*_colunas_grupo(col_agrupamento), col_fase]
    colunas = [col_consumo_diario, *grupos]
    if col_data:
        colunas.append(col_data)
    _validar_colunas(df, colunas)

    trabalho = _ordenar_para_calculo(df, grupos, col_data)
    consumo_diario = pd.to_numeric(trabalho[col_consumo_diario], errors="coerce").fillna(0.0)
    acumulado = consumo_diario.groupby(
        [trabalho[col] for col in grupos],
        sort=False,
        dropna=False,
    ).cumsum()

    acumulado = acumulado.reindex(df.index)
    acumulado.name = COLUNA_CONSUMO_RACAO_NA_FASE
    return acumulado


def calcular_tca_diario(
    df: pd.DataFrame,
    col_consumo_diario: str,
    col_ganho_biomassa_diario: str,
) -> pd.Series:
    """
    TCA Diario = Consumo Diario / Ganho de Biomassa do Dia.
    Retorna zero quando o ganho e menor ou igual a zero.
    """
    _validar_colunas(df, [col_consumo_diario, col_ganho_biomassa_diario])
    consumo = pd.to_numeric(df[col_consumo_diario], errors="coerce").fillna(0.0)
    ganho = pd.to_numeric(df[col_ganho_biomassa_diario], errors="coerce").fillna(0.0)
    tca = pd.Series(
        np.divide(
            consumo,
            ganho,
            out=np.zeros(len(df), dtype="float64"),
            where=ganho.to_numpy() > 0,
        ),
        index=df.index,
        dtype="float64",
        name=COLUNA_TCA_DIARIO,
    )
    return tca


def calcular_tca_acumulado(
    df: pd.DataFrame,
    col_consumo_acumulado: str,
    col_ganho_biomassa_acumulado: str,
    col_data: str | None = None,
    data_base: date | datetime | str | pd.Timestamp | None = None,
) -> pd.Series:
    """
    TCA Acumulado = Consumo Acumulado / Ganho de Biomassa Acumulado.

    A divisao e segura: ganho menor ou igual a zero gera TCA zero. Quando
    `data_base` for informada, linhas anteriores a ela tambem ficam zeradas.
    """
    colunas = [col_consumo_acumulado, col_ganho_biomassa_acumulado]
    if col_data:
        colunas.append(col_data)
    _validar_colunas(df, colunas)

    consumo = pd.to_numeric(df[col_consumo_acumulado], errors="coerce").fillna(0.0)
    ganho = pd.to_numeric(df[col_ganho_biomassa_acumulado], errors="coerce").fillna(0.0)
    tca = pd.Series(
        np.divide(
            consumo,
            ganho,
            out=np.zeros(len(df), dtype="float64"),
            where=ganho.to_numpy() > 0,
        ),
        index=df.index,
        dtype="float64",
        name=COLUNA_TCA_ACUMULADO,
    )

    if data_base is not None:
        tca = _serie_filtrada_por_data_base(df, tca, col_data=col_data, data_base=data_base)
        tca.name = COLUNA_TCA_ACUMULADO

    return tca


def aplicar_calculos_alimentacao(
    df: pd.DataFrame,
    *,
    col_consumo_diario: str,
    col_ganho_biomassa_acumulado: str,
    col_agrupamento: str | Sequence[str] | None,
    col_data: str | None = None,
    data_base: date | datetime | str | pd.Timestamp | None = None,
    col_fase: str | None = None,
    col_ganho_biomassa_diario: str | None = None,
) -> pd.DataFrame:
    """
    Devolve uma copia do DataFrame com consumo acumulado e TCA calculados.
    """
    resultado = df.copy()
    resultado[COLUNA_CONSUMO_RACAO_ACUMULADO] = calcular_consumo_racao_acumulado(
        resultado,
        col_consumo_diario=col_consumo_diario,
        col_agrupamento=col_agrupamento,
        col_data=col_data,
        data_base=data_base,
    )

    if col_fase:
        resultado[COLUNA_CONSUMO_RACAO_NA_FASE] = calcular_consumo_racao_acumulado_por_fase(
            resultado,
            col_consumo_diario=col_consumo_diario,
            col_fase=col_fase,
            col_agrupamento=col_agrupamento,
            col_data=col_data,
        )

    if col_ganho_biomassa_diario:
        resultado[COLUNA_TCA_DIARIO] = calcular_tca_diario(
            resultado,
            col_consumo_diario=col_consumo_diario,
            col_ganho_biomassa_diario=col_ganho_biomassa_diario,
        )

    resultado[COLUNA_TCA_ACUMULADO] = calcular_tca_acumulado(
        resultado,
        col_consumo_acumulado=COLUNA_CONSUMO_RACAO_ACUMULADO,
        col_ganho_biomassa_acumulado=col_ganho_biomassa_acumulado,
        col_data=col_data,
        data_base=data_base,
    )
    return resultado
