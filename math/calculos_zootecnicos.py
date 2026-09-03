from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd


COLUNA_BIOMASSA = "Biomassa (kg)"
COLUNA_GANHO_BIOMASSA_ACUMULADO = "Ganho de Biomassa Acumulado (kg)"
COLUNA_MORTALIDADE_DIARIA = "Mortalidade Diaria (peixes)"
COLUNA_MORTALIDADE_ACUMULADA = "Mortalidade Acumulada (peixes)"
COLUNA_QUANTIDADE_PEIXES = "Quantidade de Peixes"
COLUNA_PO_ATUALIZADO = "PO Atualizado"


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


def calcular_biomassa(
    df: pd.DataFrame,
    col_quantidade_peixes: str,
    col_peso_medio_g: str,
) -> pd.Series:
    """
    Calcula Biomassa (kg) = Quantidade de Peixes * Peso Medio (g) / 1000.
    """
    _validar_colunas(df, [col_quantidade_peixes, col_peso_medio_g])
    quantidade = pd.to_numeric(df[col_quantidade_peixes], errors="coerce").fillna(0.0)
    peso_medio = pd.to_numeric(df[col_peso_medio_g], errors="coerce").fillna(0.0)
    biomassa = quantidade * peso_medio / 1000.0
    biomassa.name = COLUNA_BIOMASSA
    return biomassa


def calcular_ganho_biomassa_acumulado(
    df: pd.DataFrame,
    col_biomassa: str,
    col_agrupamento: str | Sequence[str] | None = None,
    col_data: str | None = None,
    col_biomassa_inicial: str | None = None,
) -> pd.Series:
    """
    Calcula o ganho acumulado como Biomassa atual - Biomassa inicial do lote.

    Quando `col_biomassa_inicial` nao for informada, a primeira biomassa de
    cada grupo, na ordem recebida ou na ordem de `col_data`, sera usada como
    biomassa inicial.
    """
    colunas = [col_biomassa, *_colunas_grupo(col_agrupamento)]
    if col_data:
        colunas.append(col_data)
    if col_biomassa_inicial:
        colunas.append(col_biomassa_inicial)
    _validar_colunas(df, colunas)

    trabalho = _ordenar_para_calculo(df, col_agrupamento, col_data)
    biomassa = pd.to_numeric(trabalho[col_biomassa], errors="coerce").fillna(0.0)

    if col_biomassa_inicial:
        biomassa_inicial = pd.to_numeric(trabalho[col_biomassa_inicial], errors="coerce").fillna(0.0)
    else:
        grupos = _colunas_grupo(col_agrupamento)
        if grupos:
            biomassa_inicial = biomassa.groupby(
                [trabalho[col] for col in grupos],
                sort=False,
                dropna=False,
            ).transform("first")
        else:
            biomassa_inicial = pd.Series(
                biomassa.iloc[0] if not biomassa.empty else 0.0,
                index=trabalho.index,
                dtype="float64",
            )

    ganho = biomassa - biomassa_inicial
    ganho = ganho.reindex(df.index)
    ganho.name = COLUNA_GANHO_BIOMASSA_ACUMULADO
    return ganho


def calcular_decaimento_populacional(
    df: pd.DataFrame,
    col_quantidade_inicial: str,
    col_mortalidade_pct: str,
    col_agrupamento: str | Sequence[str] | None = None,
    col_data: str | None = None,
) -> pd.DataFrame:
    """
    Reproduz o decaimento populacional diario do simulador.

    Para cada linha:
    - mortos_dia = quantidade_ativa_antes_do_dia * mortalidade_pct / 100
    - quantidade_ativa = max(quantidade_ativa_antes_do_dia - mortos_dia, 0)
    - mortalidade_acumulada += mortos_dia

    Retorna um DataFrame alinhado ao indice original com quantidade ativa,
    mortalidade diaria e mortalidade acumulada.
    """
    colunas = [col_quantidade_inicial, col_mortalidade_pct, *_colunas_grupo(col_agrupamento)]
    if col_data:
        colunas.append(col_data)
    _validar_colunas(df, colunas)

    trabalho = _ordenar_para_calculo(df, col_agrupamento, col_data)
    grupos = _colunas_grupo(col_agrupamento)
    partes: list[pd.DataFrame] = []

    if grupos:
        iterador = trabalho.groupby(grupos, sort=False, dropna=False)
    else:
        iterador = [(None, trabalho)]

    for _, grupo in iterador:
        quantidade_inicial = pd.to_numeric(
            grupo[col_quantidade_inicial],
            errors="coerce",
        ).fillna(0.0)
        mortalidade_pct = pd.to_numeric(
            grupo[col_mortalidade_pct],
            errors="coerce",
        ).fillna(0.0).clip(lower=0.0)

        quantidade_ativa = float(quantidade_inicial.iloc[0]) if not grupo.empty else 0.0
        mortalidade_acumulada = 0.0
        linhas: list[dict[str, float]] = []

        for pct in mortalidade_pct:
            mortos_dia = quantidade_ativa * (float(pct) / 100.0)
            quantidade_ativa = max(quantidade_ativa - mortos_dia, 0.0)
            mortalidade_acumulada += mortos_dia
            linhas.append(
                {
                    COLUNA_QUANTIDADE_PEIXES: quantidade_ativa,
                    COLUNA_MORTALIDADE_DIARIA: mortos_dia,
                    COLUNA_MORTALIDADE_ACUMULADA: mortalidade_acumulada,
                }
            )

        partes.append(pd.DataFrame(linhas, index=grupo.index))

    if not partes:
        return pd.DataFrame(
            columns=[
                COLUNA_QUANTIDADE_PEIXES,
                COLUNA_MORTALIDADE_DIARIA,
                COLUNA_MORTALIDADE_ACUMULADA,
            ],
            index=df.index,
        )

    return pd.concat(partes).reindex(df.index)


def calcular_mortalidade_acumulada(
    df: pd.DataFrame,
    col_quantidade_inicial: str,
    col_mortalidade_pct: str,
    col_agrupamento: str | Sequence[str] | None = None,
    col_data: str | None = None,
) -> pd.Series:
    resultado = calcular_decaimento_populacional(
        df,
        col_quantidade_inicial=col_quantidade_inicial,
        col_mortalidade_pct=col_mortalidade_pct,
        col_agrupamento=col_agrupamento,
        col_data=col_data,
    )[COLUNA_MORTALIDADE_ACUMULADA]
    resultado.name = COLUNA_MORTALIDADE_ACUMULADA
    return resultado


def calcular_po_atualizado(df: pd.DataFrame, col_po_preenchido: str) -> pd.Series:
    """
    PO Atualizado = PO preenchido manualmente na tabela.
    """
    _validar_colunas(df, [col_po_preenchido])
    po = pd.to_numeric(df[col_po_preenchido], errors="coerce").fillna(0.0)
    po.name = COLUNA_PO_ATUALIZADO
    return po


def aplicar_calculos_zootecnicos(
    df: pd.DataFrame,
    *,
    col_quantidade_peixes: str,
    col_peso_medio_g: str,
    col_biomassa: str = COLUNA_BIOMASSA,
    col_agrupamento: str | Sequence[str] | None = None,
    col_data: str | None = None,
    col_mortalidade_pct: str | None = None,
    col_po_preenchido: str | None = None,
) -> pd.DataFrame:
    """
    Devolve uma copia do DataFrame com as colunas zootecnicas calculadas.
    """
    resultado = df.copy()
    resultado[col_biomassa] = calcular_biomassa(resultado, col_quantidade_peixes, col_peso_medio_g)
    resultado[COLUNA_GANHO_BIOMASSA_ACUMULADO] = calcular_ganho_biomassa_acumulado(
        resultado,
        col_biomassa=col_biomassa,
        col_agrupamento=col_agrupamento,
        col_data=col_data,
    )

    if col_mortalidade_pct:
        decaimento = calcular_decaimento_populacional(
            resultado,
            col_quantidade_inicial=col_quantidade_peixes,
            col_mortalidade_pct=col_mortalidade_pct,
            col_agrupamento=col_agrupamento,
            col_data=col_data,
        )
        for coluna in decaimento.columns:
            resultado[coluna] = decaimento[coluna]

    if col_po_preenchido:
        resultado[COLUNA_PO_ATUALIZADO] = calcular_po_atualizado(resultado, col_po_preenchido)

    return resultado
