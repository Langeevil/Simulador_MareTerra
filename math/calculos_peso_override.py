from datetime import timedelta
from math import ceil, isfinite
from typing import Any, Optional

import numpy as np
import pandas as pd


PESO_COL = "peso_medio_g"
BIOMASSA_COL = "biomassa_kg"
DATA_COL = "data"
MES_COL = "mes"
STATUS_COL = "status"

VAZIO_SANITARIO_DIAS = 5
GDP_PADRAO_G_DIA = 3.0
LIMITE_DIAS_EXTRAS = 730


def _normalizar_mes(mes: Any) -> Optional[str]:
    """
    Converte formatos como:
    - '2026-09'
    - '09/2026'
    - Timestamp

    Para o formato padrão:
    - 'YYYY-MM'
    """
    if mes is None or pd.isna(mes):
        return None

    if isinstance(mes, pd.Timestamp):
        return mes.strftime("%Y-%m")

    texto = str(mes).strip()

    if not texto:
        return None

    if "/" in texto:
        partes = texto.split("/")
        if len(partes) == 2:
            mes_num, ano = partes
            return f"{ano.strip()}-{mes_num.strip().zfill(2)}"

    try:
        return pd.Period(texto, freq="M").strftime("%Y-%m")
    except Exception:
        return texto


def _coluna_quantidade(df: pd.DataFrame) -> Optional[str]:
    """
    Tenta descobrir qual coluna representa a quantidade de peixes.
    """
    candidatos = [
        "quantidade de peixes",
        "quantidade_peixes",
        "qtd_peixes",
        "qtd",
    ]

    for col in candidatos:
        if col in df.columns:
            return col

    return None
def _mask_produtor_atual(df: pd.DataFrame, regiao: str, produtor: str) -> pd.Series:
    """
    Cria uma máscara atualizada para região/produtor.

    Importante:
    essa máscara precisa ser recriada sempre que o DataFrame muda de tamanho.
    """
    return (
        df["regiao_calc"].astype(str).eq(str(regiao))
        & df["produtor"].astype(str).eq(str(produtor))
    )


def _mask_tanque_atual(
    df: pd.DataFrame,
    regiao: str,
    produtor: str,
    tanque: str,
) -> pd.Series:
    """
    Cria uma máscara atualizada para região/produtor/tanque.

    Evita erro de tamanho quando o DataFrame recebeu linhas novas
    ou teve linhas removidas.
    """
    return (
        df["regiao_calc"].astype(str).eq(str(regiao))
        & df["produtor"].astype(str).eq(str(produtor))
        & df["tanque"].astype(str).eq(str(tanque))
    )

def _calcular_gdp_referencia(df_tanque_sorted: pd.DataFrame) -> float:
    """
    Calcula um GDP de referência com base nos últimos registros positivos
    do próprio tanque.

    Isso permite continuar o crescimento depois do ponto em que o relatório
    original parou nos 900g.
    """
    dados = df_tanque_sorted[[DATA_COL, PESO_COL]].copy()

    dados[DATA_COL] = pd.to_datetime(dados[DATA_COL], errors="coerce")
    dados[PESO_COL] = pd.to_numeric(dados[PESO_COL], errors="coerce")

    dados = dados.dropna(subset=[DATA_COL, PESO_COL]).sort_values(DATA_COL)

    if len(dados) < 2:
        return GDP_PADRAO_G_DIA

    dias = dados[DATA_COL].diff().dt.days
    ganhos = dados[PESO_COL].diff()

    gdps = ganhos / dias.replace(0, np.nan)
    gdps = gdps.replace([np.inf, -np.inf], np.nan).dropna()
    gdps = gdps[gdps > 0]

    if gdps.empty:
        return GDP_PADRAO_G_DIA

    gdp = float(gdps.tail(7).median())

    if isfinite(gdp) and gdp > 0:
        return gdp

    return GDP_PADRAO_G_DIA


def _atualizar_campos_derivados(
    linha: pd.Series,
    nova_data: pd.Timestamp,
    novo_peso: float,
    data_inicial: pd.Timestamp,
    peso_inicial: float,
    quantidade_col: Optional[str],
    biomassa_base: float,
    peso_base: float,
    gdp: float,
) -> pd.Series:
    """
    Atualiza campos derivados em uma nova linha extrapolada.
    """
    linha[DATA_COL] = nova_data
    linha[PESO_COL] = float(novo_peso)
    linha[MES_COL] = nova_data.strftime("%Y-%m")

    if "ano" in linha.index:
        linha["ano"] = int(nova_data.year)

    if "semana" in linha.index and pd.notna(data_inicial):
        dias_totais = max((nova_data - data_inicial).days + 1, 1)
        linha["semana"] = int(((dias_totais - 1) // 7) + 1)

    if quantidade_col and quantidade_col in linha.index:
        quantidade = pd.to_numeric(
            pd.Series([linha[quantidade_col]]),
            errors="coerce"
        ).iloc[0]

        if pd.notna(quantidade):
            linha[BIOMASSA_COL] = float(quantidade) * float(novo_peso) / 1000.0

    elif BIOMASSA_COL in linha.index and peso_base > 0:
        linha[BIOMASSA_COL] = biomassa_base * (float(novo_peso) / peso_base)

    if "gdp_diario_g_dia" in linha.index:
        linha["gdp_diario_g_dia"] = float(gdp)

    if "gdp acumulado (g)" in linha.index:
        dias_cultivo = max((nova_data - data_inicial).days, 1)
        linha["gdp acumulado (g)"] = (float(novo_peso) - peso_inicial) / dias_cultivo

    if "gdp_acumulado_g" in linha.index:
        dias_cultivo = max((nova_data - data_inicial).days, 1)
        linha["gdp_acumulado_g"] = (float(novo_peso) - peso_inicial) / dias_cultivo

    linha[STATUS_COL] = ""

    if "tanques_liberados" in linha.index:
        linha["tanques_liberados"] = ""

    if "tanques_disponivel" in linha.index:
        linha["tanques_disponivel"] = ""

    return linha

def _cortar_linhas_apos_primeiro_peixe_pronto(df: pd.DataFrame) -> pd.DataFrame:
    """
    Remove todas as linhas posteriores ao primeiro status 'Peixe Pronto'
    de cada tanque.

    Regra:
    se um tanque atingiu Peixe Pronto em uma data, ele foi despescado.
    Portanto, não deve continuar crescendo nos dias seguintes.
    """
    if df is None or df.empty:
        return df

    if STATUS_COL not in df.columns or DATA_COL not in df.columns:
        return df

    chaves = ["regiao_calc", "produtor", "tanque"]

    for col in chaves:
        if col not in df.columns:
            return df

    df = df.copy()
    df[DATA_COL] = pd.to_datetime(df[DATA_COL], errors="coerce")

    indices_remover = []

    for _, grupo in df.groupby(chaves, dropna=False, sort=False):
        grupo = grupo.dropna(subset=[DATA_COL]).sort_values(DATA_COL)

        if grupo.empty:
            continue

        status_pronto = (
            grupo[STATUS_COL]
            .astype(str)
            .str.strip()
            .str.lower()
            .eq("peixe pronto")
        )

        if not status_pronto.any():
            continue

        primeira_data_pronto = grupo.loc[status_pronto, DATA_COL].min()

        idx_futuros = grupo.index[grupo[DATA_COL] > primeira_data_pronto]

        indices_remover.extend(idx_futuros.tolist())

    if indices_remover:
        df = df.drop(index=indices_remover).reset_index(drop=True)

    return df

def aplicar_overrides_peso_medio(
    df_base: pd.DataFrame,
    overrides: dict[str, dict[str, dict[str, float]]],
) -> pd.DataFrame:
    if df_base is None or df_base.empty or not overrides:
        return df_base.copy() if df_base is not None else pd.DataFrame()

    required = {"regiao_calc", "produtor", "tanque", DATA_COL, PESO_COL}
    missing = required - set(df_base.columns)

    if missing:
        raise ValueError(
            f"DataFrame base sem colunas obrigatórias para override: {sorted(missing)}"
        )

    df = df_base.copy()

    df[DATA_COL] = pd.to_datetime(df[DATA_COL], errors="coerce")
    df[PESO_COL] = pd.to_numeric(df[PESO_COL], errors="coerce")

    if BIOMASSA_COL in df.columns:
        df[BIOMASSA_COL] = pd.to_numeric(df[BIOMASSA_COL], errors="coerce").fillna(0.0)

    if MES_COL not in df.columns:
        df[MES_COL] = df[DATA_COL].dt.strftime("%Y-%m")

    quantidade_col = _coluna_quantidade(df)

    if quantidade_col:
        df[quantidade_col] = pd.to_numeric(df[quantidade_col], errors="coerce")

    for regiao, produtores in (overrides or {}).items():
        if not produtores:
            continue

        for produtor, meses in produtores.items():
            if not meses:
                continue

            metas_validas = []

            for mes, peso in meses.items():
                peso_num = pd.to_numeric(pd.Series([peso]), errors="coerce").iloc[0]

                if pd.isna(peso_num) or float(peso_num) <= 0:
                    continue

                mes_norm = _normalizar_mes(mes)

                if not mes_norm:
                    continue

                metas_validas.append((mes_norm, float(peso_num)))

            if not metas_validas:
                continue

            metas_validas = sorted(metas_validas, key=lambda item: item[0])
            maior_peso_alvo = max(peso for _, peso in metas_validas)

            mask_produtor = (
                df["regiao_calc"].astype(str).eq(str(regiao))
                & df["produtor"].astype(str).eq(str(produtor))
            )

            tanques_do_produtor = df.loc[
                mask_produtor,
                "tanque"
            ].dropna().unique()

            for tanque in tanques_do_produtor:
                mask_tanque = (
                    df["regiao_calc"].astype(str).eq(str(regiao))
                    & df["produtor"].astype(str).eq(str(produtor))
                    & df["tanque"].astype(str).eq(str(tanque))
                )

                df_tanque = df.loc[mask_tanque].dropna(
                    subset=[DATA_COL, PESO_COL]
                ).copy()

                if df_tanque.empty:
                    continue

                df_tanque_sorted = df_tanque.sort_values(DATA_COL)

                # Limpa somente o antigo Peixe Pronto do simulador original.
                # Não cria "Em engorda" e não apaga Class 1 / Class 2.
                status_pronto_antigo = (
                    mask_tanque
                    & df[STATUS_COL].astype(str).str.strip().str.lower().eq("peixe pronto")
                )

                df.loc[status_pronto_antigo, STATUS_COL] = ""

                if "tanques_liberados" in df.columns:
                    df.loc[status_pronto_antigo, "tanques_liberados"] = ""

                if "tanques_disponivel" in df.columns:
                    df.loc[status_pronto_antigo, "tanques_disponivel"] = ""

                peso_maximo = float(df_tanque_sorted[PESO_COL].max())

                # Se algum peso digitado for maior que o último peso calculado,
                # cria dias extras até o maior alvo.
                if maior_peso_alvo > peso_maximo:
                    ultima_linha = df_tanque_sorted.iloc[-1].copy()
                    ultima_data = pd.to_datetime(ultima_linha[DATA_COL], errors="coerce")

                    peso_base = float(ultima_linha[PESO_COL])
                    biomassa_base = float(ultima_linha.get(BIOMASSA_COL, 0.0) or 0.0)

                    gdp = _calcular_gdp_referencia(df_tanque_sorted)

                    dias_extras = int(ceil((maior_peso_alvo - peso_base) / gdp))
                    dias_extras = max(1, min(dias_extras, LIMITE_DIAS_EXTRAS))

                    novas_linhas = []

                    for i in range(1, dias_extras + 1):
                        nova_data = ultima_data + timedelta(days=i)
                        peso_estimado = peso_base + (gdp * i)

                        if i == dias_extras or peso_estimado >= maior_peso_alvo:
                            peso_estimado = maior_peso_alvo

                        nova_linha = ultima_linha.copy()

                        nova_linha[DATA_COL] = nova_data
                        nova_linha[PESO_COL] = float(peso_estimado)
                        nova_linha[MES_COL] = nova_data.strftime("%Y-%m")

                        if "ano" in nova_linha.index:
                            nova_linha["ano"] = int(nova_data.year)

                        if "semana" in nova_linha.index:
                            primeira_data = pd.to_datetime(
                                df_tanque_sorted.iloc[0][DATA_COL],
                                errors="coerce"
                            )

                            if pd.notna(primeira_data):
                                dias_totais = max((nova_data - primeira_data).days + 1, 1)
                                nova_linha["semana"] = int(((dias_totais - 1) // 7) + 1)

                        if BIOMASSA_COL in nova_linha.index and peso_base > 0:
                            nova_linha[BIOMASSA_COL] = biomassa_base * (
                                float(peso_estimado) / peso_base
                            )

                        if "gdp_diario_g_dia" in nova_linha.index:
                            nova_linha["gdp_diario_g_dia"] = float(gdp)

                        # Não cria status novo.
                        nova_linha[STATUS_COL] = ""

                        if "tanques_liberados" in nova_linha.index:
                            nova_linha["tanques_liberados"] = ""

                        if "tanques_disponivel" in nova_linha.index:
                            nova_linha["tanques_disponivel"] = ""

                        novas_linhas.append(nova_linha)

                        if peso_estimado >= maior_peso_alvo:
                            break

                    if novas_linhas:
                        df = pd.concat(
                            [df, pd.DataFrame(novas_linhas)],
                            ignore_index=True
                        )

                # Recalcula o tanque depois da extrapolação.
                mask_tanque = (
                    df["regiao_calc"].astype(str).eq(str(regiao))
                    & df["produtor"].astype(str).eq(str(produtor))
                    & df["tanque"].astype(str).eq(str(tanque))
                )

                df_tanque = df.loc[mask_tanque].dropna(
                    subset=[DATA_COL, PESO_COL]
                ).copy()

                if df_tanque.empty:
                    continue

                df_tanque_sorted = df_tanque.sort_values(DATA_COL)

                datas_peixe_pronto = []

                # Agora avalia as metas mês a mês para cada tanque.
                # Regra:
                # - a meta de 06/2026 só vale dentro de 06/2026;
                # - a meta de 07/2026 só vale dentro de 07/2026;
                # - a meta de 08/2026 só vale dentro de 08/2026;
                # - se o tanque ficar pronto em um mês, ele é despescado e para ali.
                data_peixe_pronto_tanque = None
                
                for mes_norm, novo_peso in metas_validas:
                    periodo_meta = pd.Period(mes_norm, freq="M")
                    data_inicio_meta = periodo_meta.start_time.normalize()
                    data_fim_meta = periodo_meta.end_time.normalize()
                
                    # Aqui está a correção principal:
                    # procura somente dentro do mês da meta.
                    df_mes = df_tanque_sorted[
                        (df_tanque_sorted[DATA_COL] >= data_inicio_meta)
                        & (df_tanque_sorted[DATA_COL] <= data_fim_meta)
                    ].copy()
                
                    if df_mes.empty:
                        continue
                
                    df_mes[PESO_COL] = pd.to_numeric(df_mes[PESO_COL], errors="coerce")
                
                    # Só considera pronto se atingiu ou passou o peso alvo daquele mês.
                    # Não marca 500g, 600g, 700g como pronto se o alvo era 850g.
                    df_atingiu_meta = df_mes[df_mes[PESO_COL] >= novo_peso].copy()
                
                    if df_atingiu_meta.empty:
                        # Não atingiu a meta dentro desse mês.
                        # Então continua vivo para ser avaliado no próximo mês.
                        continue
                
                    # Como pode passar um pouco do alvo, escolhe o registro mais próximo.
                    df_atingiu_meta["_diff_peso_alvo"] = (
                        df_atingiu_meta[PESO_COL] - novo_peso
                    ).abs()
                
                    idx_mais_proximo = df_atingiu_meta.sort_values(
                        ["_diff_peso_alvo", DATA_COL]
                    ).index[0]
                
                    data_escolhida = pd.to_datetime(
                        df.loc[idx_mais_proximo, DATA_COL],
                        errors="coerce"
                    )
                
                    if pd.isna(data_escolhida):
                        continue
                
                    df.loc[idx_mais_proximo, STATUS_COL] = "Peixe Pronto"
                
                    if "tanques_liberados" in df.columns:
                        df.loc[idx_mais_proximo, "tanques_liberados"] = (
                            data_escolhida + timedelta(days=1)
                        ).strftime("%d/%m/%Y")
                
                    if "tanques_disponivel" in df.columns:
                        df.loc[idx_mais_proximo, "tanques_disponivel"] = (
                            data_escolhida + timedelta(days=1 + VAZIO_SANITARIO_DIAS)
                        ).strftime("%d/%m/%Y")
                
                    data_peixe_pronto_tanque = data_escolhida
                
                    # Achou Peixe Pronto para esse tanque.
                    # Para de avaliar os próximos meses desse mesmo tanque.
                    break
                # Só remove o futuro depois do último alvo informado.
                # Assim junho e julho não são apagados quando agosto é processado.
                if data_peixe_pronto_tanque is not None:
                    mask_tanque = (
                        df["regiao_calc"].astype(str).eq(str(regiao))
                        & df["produtor"].astype(str).eq(str(produtor))
                        & df["tanque"].astype(str).eq(str(tanque))
                    )
                
                    mask_delete = mask_tanque & (df[DATA_COL] > data_peixe_pronto_tanque)
                
                    if mask_delete.any():
                        df = df.loc[~mask_delete].copy().reset_index(drop=True)
                        
    df = _cortar_linhas_apos_primeiro_peixe_pronto(df)

    return df.sort_values(
        ["regiao_calc", "produtor", "tanque", DATA_COL]
    ).reset_index(drop=True)