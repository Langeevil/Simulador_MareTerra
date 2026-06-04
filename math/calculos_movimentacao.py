from __future__ import annotations

from collections.abc import Mapping, Sequence

import numpy as np
import pandas as pd


VAZIO_SANITARIO_DIAS = 5
STATUS_BIOMETRIA = "Biometria"
STATUS_TANQUE_DISPONIVEL = "Tanque Disponivel"
COLUNA_DATA_TANQUE_DISPONIVEL = "Data Tanque Disponivel"
COLUNA_TANQUES_DISPONIVEL = "Tanques Disponivel"
COLUNA_SALDO_ACUMULADO_MES = "Saldo Acumulado Atualizado do Mes"


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


def calcular_data_tanque_disponivel(
    df: pd.DataFrame,
    col_data: str,
    col_tanque_liberado: str,
    dias_vazio_sanitario: int = VAZIO_SANITARIO_DIAS,
) -> pd.Series:
    """
    Calcula Data Tanque Disponivel = Data do Tanque Liberado + dias de vazio.

    A data e preenchida somente nas linhas em que `col_tanque_liberado` vale 1.
    """
    _validar_colunas(df, [col_data, col_tanque_liberado])

    datas = pd.to_datetime(df[col_data], errors="coerce")
    liberado = pd.to_numeric(df[col_tanque_liberado], errors="coerce").fillna(0).astype(int).eq(1)
    data_disponivel = datas + pd.to_timedelta(int(dias_vazio_sanitario), unit="D")
    resultado = data_disponivel.where(liberado, pd.NaT)
    resultado.name = COLUNA_DATA_TANQUE_DISPONIVEL
    return resultado


def calcular_flag_tanque_disponivel_por_vazio(
    df: pd.DataFrame,
    col_data: str,
    col_tanque_liberado: str,
    col_agrupamento: str | Sequence[str] | None,
    dias_vazio_sanitario: int = VAZIO_SANITARIO_DIAS,
) -> pd.Series:
    """
    Marca 1 na linha cuja data coincide com a liberacao + vazio sanitario.

    Esta funcao preserva a regra historica do simulador, que cria uma linha no
    quinto dia do vazio sanitario e marca `Tanques Disponivel = 1`.
    """
    grupos = _colunas_grupo(col_agrupamento)
    _validar_colunas(df, [col_data, col_tanque_liberado, *grupos])

    trabalho = df.copy()
    trabalho["_data_calc"] = pd.to_datetime(trabalho[col_data], errors="coerce")
    trabalho["_liberado_calc"] = pd.to_numeric(
        trabalho[col_tanque_liberado],
        errors="coerce",
    ).fillna(0).astype(int)
    trabalho["_data_disponivel_calc"] = calcular_data_tanque_disponivel(
        trabalho,
        col_data="_data_calc",
        col_tanque_liberado="_liberado_calc",
        dias_vazio_sanitario=dias_vazio_sanitario,
    )

    if grupos:
        datas_liberadas = trabalho.loc[
            trabalho["_liberado_calc"].eq(1),
            [*grupos, "_data_disponivel_calc"],
        ].dropna(subset=["_data_disponivel_calc"])
        if datas_liberadas.empty:
            disponivel = pd.Series(0, index=df.index, dtype="int64", name=COLUNA_TANQUES_DISPONIVEL)
            return disponivel

        chave = [*grupos, "_data_calc"]
        datas_liberadas = datas_liberadas.rename(columns={"_data_disponivel_calc": "_data_calc"})
        marcadores = datas_liberadas.drop_duplicates(chave).assign(_disponivel_calc=1)
        trabalho = trabalho.merge(marcadores, on=chave, how="left", sort=False)
        disponivel = trabalho["_disponivel_calc"].fillna(0).astype(int)
        disponivel.index = df.index
    else:
        datas_disponiveis = set(trabalho["_data_disponivel_calc"].dropna())
        disponivel = trabalho["_data_calc"].isin(datas_disponiveis).astype(int)

    disponivel.name = COLUNA_TANQUES_DISPONIVEL
    return disponivel.reindex(df.index).fillna(0).astype(int)


def calcular_gatilho_biometria(
    df: pd.DataFrame,
    col_data: str,
    col_data_ultima_biometria: str,
) -> pd.Series:
    """
    Retorna True quando a data da linha cruza a data da ultima biometria.
    """
    _validar_colunas(df, [col_data, col_data_ultima_biometria])
    data_linha = pd.to_datetime(df[col_data], errors="coerce").dt.normalize()
    data_biometria = pd.to_datetime(df[col_data_ultima_biometria], errors="coerce").dt.normalize()
    gatilho = data_linha.eq(data_biometria) & data_linha.notna()
    gatilho.name = "Gatilho Biometria"
    return gatilho


def calcular_saldo_acumulado_mes(
    df: pd.DataFrame,
    col_saldo_dia: str,
    col_dias_abate: str,
    col_agrupamento: str | Sequence[str],
) -> pd.Series:
    """
    Calcula o saldo acumulado mensal por grupo.

    Regra:
    Saldo Acumulado Atualizado do Mes =
    (Saldo Acumulado do Dia * Dias de Abate) + Saldo Acumulado do Mes Anterior

    O DataFrame deve chegar ordenado na sequencia temporal desejada dentro de
    cada agrupamento, pois o mes anterior e obtido com groupby().shift(1).
    """
    colunas_agrupamento = _colunas_grupo(col_agrupamento)
    if not colunas_agrupamento:
        raise ValueError("Informe pelo menos uma coluna de agrupamento para calcular o saldo acumulado.")

    _validar_colunas(df, [col_saldo_dia, col_dias_abate, *colunas_agrupamento])

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


def calcular_saldo_acumulado_consolidado(
    saldo_acumulado_apt: Mapping[str, float] | pd.Series,
    saldo_acumulado_ita: Mapping[str, float] | pd.Series,
    meses: Sequence[str] | None = None,
) -> dict[str, float]:
    """
    Calcula o consolidado pela soma direta dos saldos acumulados regionais.

    Regra:
    Saldo Acm Atualizado / Mes Consolidado =
    Saldo Acm Atualizado / Mes APT + Saldo Acm Atualizado / Mes ITA
    """
    # Regra anterior do consolidado, mantida comentada para rastreabilidade:
    # geral_saldo_dia = total_dia_geral - po_geral
    # geral_dias_abate = apt["dias"]
    # geral_saldo_acm = calcular_saldo_acumulado_mes(
    #     df_geral_saldo_mes,
    #     col_saldo_dia="Saldo PO Atualizado",
    #     col_dias_abate="Dias de Abate",
    #     col_agrupamento="Grupo",
    # )

    def chaves(valores: Mapping[str, float] | pd.Series) -> list[str]:
        if isinstance(valores, pd.Series):
            return list(valores.index)
        return list(valores.keys())

    def valor_mes(valores: Mapping[str, float] | pd.Series, mes: str) -> float:
        bruto = valores.get(mes, 0.0)
        numero = pd.to_numeric(bruto, errors="coerce")
        return 0.0 if pd.isna(numero) else float(numero)

    meses_calculo = list(meses) if meses is not None else list(
        dict.fromkeys([*chaves(saldo_acumulado_apt), *chaves(saldo_acumulado_ita)])
    )
    return {
        mes: valor_mes(saldo_acumulado_apt, mes) + valor_mes(saldo_acumulado_ita, mes)
        for mes in meses_calculo
    }


def calcular_po_atualizado_no_mes_saldo_consolidado(
    saldo_po_atualizado_geral: Mapping[str, float] | pd.Series,
    dias_abate_ita: Mapping[str, float] | pd.Series,
    meses: Sequence[str] | None = None,
) -> dict[str, float]:
    """
    Calcula a linha PO Atualizado (No Mes) Saldo do consolidado.

    Regra:
    PO Atualizado (No Mes) Saldo =
    Saldo PO Atualizado do quadro geral diario * Dias de Abate da ITA
    """
    # Regra anterior, mantida comentada para rastreabilidade:
    # geral_total_mes = total_mes_apt + total_mes_ita
    # geral_abate_po_mes = (po_apt * dias_apt) + (po_ita * dias_ita)
    # geral_saldo_mes = geral_total_mes - geral_abate_po_mes

    def chaves(valores: Mapping[str, float] | pd.Series) -> list[str]:
        if isinstance(valores, pd.Series):
            return list(valores.index)
        return list(valores.keys())

    def valor_mes(valores: Mapping[str, float] | pd.Series, mes: str) -> float:
        bruto = valores.get(mes, 0.0)
        numero = pd.to_numeric(bruto, errors="coerce")
        return 0.0 if pd.isna(numero) else float(numero)

    meses_calculo = list(meses) if meses is not None else list(
        dict.fromkeys([*chaves(saldo_po_atualizado_geral), *chaves(dias_abate_ita)])
    )
    return {
        mes: valor_mes(saldo_po_atualizado_geral, mes) * valor_mes(dias_abate_ita, mes)
        for mes in meses_calculo
    }


def calcular_total_kg_mes_disponivel_abate_consolidado(
    total_kg_dia_apt: Mapping[str, float] | pd.Series,
    dias_abate_apt: Mapping[str, float] | pd.Series,
    total_kg_dia_ita: Mapping[str, float] | pd.Series,
    dias_abate_ita: Mapping[str, float] | pd.Series,
    meses: Sequence[str] | None = None,
) -> dict[str, float]:
    """
    Calcula Total Kg/Mes Disponivel Abate do consolidado conforme a planilha.

    Regra:
    (Total Kg/Dia Dispon Abate APT * Dias de Abate APT)
    + (Total Kg/Dia Dispon Abate ITA * Dias de Abate ITA)
    """
    # Regra anterior, mantida comentada para rastreabilidade:
    # geral_total_mes = total_mes_apt + total_mes_ita

    def chaves(valores: Mapping[str, float] | pd.Series) -> list[str]:
        if isinstance(valores, pd.Series):
            return list(valores.index)
        return list(valores.keys())

    def valor_mes(valores: Mapping[str, float] | pd.Series, mes: str) -> float:
        bruto = valores.get(mes, 0.0)
        numero = pd.to_numeric(bruto, errors="coerce")
        return 0.0 if pd.isna(numero) else float(numero)

    meses_calculo = list(meses) if meses is not None else list(
        dict.fromkeys(
            [
                *chaves(total_kg_dia_apt),
                *chaves(dias_abate_apt),
                *chaves(total_kg_dia_ita),
                *chaves(dias_abate_ita),
            ]
        )
    )
    return {
        mes: (
            valor_mes(total_kg_dia_apt, mes) * valor_mes(dias_abate_apt, mes)
            + valor_mes(total_kg_dia_ita, mes) * valor_mes(dias_abate_ita, mes)
        )
        for mes in meses_calculo
    }


def referenciar_saldo_atualizado_dia(
    saldo_atualizado_dia: Mapping[str, float] | pd.Series,
    meses: Sequence[str] | None = None,
) -> dict[str, float]:
    """
    Copia mes a mes o Saldo Atualizado / dia de uma aba regional.

    Regra usada no consolidado para referenciar uma linha ja calculada, como
    uma celula de outra aba no Excel.
    """
    # Regra anterior, mantida comentada para rastreabilidade:
    # saldo_po_atual_x_disponivel = saldo_atualizado_dia * dias_abate

    def valor_mes(valores: Mapping[str, float] | pd.Series, mes: str) -> float:
        bruto = valores.get(mes, 0.0)
        numero = pd.to_numeric(bruto, errors="coerce")
        return 0.0 if pd.isna(numero) else float(numero)

    meses_calculo = list(meses) if meses is not None else list(saldo_atualizado_dia.keys())
    return {mes: valor_mes(saldo_atualizado_dia, mes) for mes in meses_calculo}


def calcular_status_com_biometria(
    df: pd.DataFrame,
    col_status: str,
    col_data: str,
    col_data_ultima_biometria: str,
    status_biometria: str = STATUS_BIOMETRIA,
    preservar_status: Sequence[str] = ("Peixe Pronto", "Class 1", "Class 2", STATUS_TANQUE_DISPONIVEL),
) -> pd.Series:
    """
    Atualiza o status para biometria quando Data == Data Ultima Biometria.

    Por padrao, status operacionais de maior prioridade sao preservados para
    manter a mesma hierarquia descrita no simulador atual.
    """
    _validar_colunas(df, [col_status, col_data, col_data_ultima_biometria])
    status = df[col_status].fillna("").astype(str).copy()
    gatilho = calcular_gatilho_biometria(df, col_data, col_data_ultima_biometria)

    status_normalizado = status.str.strip().str.lower()
    preservar_normalizado = {str(valor).strip().lower() for valor in preservar_status}
    pode_substituir = ~status_normalizado.isin(preservar_normalizado)

    status.loc[gatilho & pode_substituir] = status_biometria
    status.name = col_status
    return status


def aplicar_vazio_sanitario(
    df: pd.DataFrame,
    *,
    col_data: str,
    col_tanque_liberado: str,
    col_agrupamento: str | Sequence[str] | None = None,
    dias_vazio_sanitario: int = VAZIO_SANITARIO_DIAS,
    col_saida_data_disponivel: str = COLUNA_DATA_TANQUE_DISPONIVEL,
    col_saida_tanques_disponivel: str | None = None,
) -> pd.DataFrame:
    """
    Devolve uma copia do DataFrame com a data de disponibilidade calculada.
    """
    resultado = df.copy()
    resultado[col_saida_data_disponivel] = calcular_data_tanque_disponivel(
        resultado,
        col_data=col_data,
        col_tanque_liberado=col_tanque_liberado,
        dias_vazio_sanitario=dias_vazio_sanitario,
    )

    if col_saida_tanques_disponivel:
        resultado[col_saida_tanques_disponivel] = calcular_flag_tanque_disponivel_por_vazio(
            resultado,
            col_data=col_data,
            col_tanque_liberado=col_tanque_liberado,
            col_agrupamento=col_agrupamento,
            dias_vazio_sanitario=dias_vazio_sanitario,
        )

    return resultado


def aplicar_status_biometria(
    df: pd.DataFrame,
    *,
    col_status: str,
    col_data: str,
    col_data_ultima_biometria: str,
    status_biometria: str = STATUS_BIOMETRIA,
    preservar_status: Sequence[str] = ("Peixe Pronto", "Class 1", "Class 2", STATUS_TANQUE_DISPONIVEL),
) -> pd.DataFrame:
    """
    Devolve uma copia do DataFrame com o gatilho de biometria aplicado.
    """
    resultado = df.copy()
    resultado[col_status] = calcular_status_com_biometria(
        resultado,
        col_status=col_status,
        col_data=col_data,
        col_data_ultima_biometria=col_data_ultima_biometria,
        status_biometria=status_biometria,
        preservar_status=preservar_status,
    )
    return resultado
