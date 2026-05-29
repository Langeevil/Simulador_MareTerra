from __future__ import annotations

import argparse
import base64
import csv
import html
import io
import sys
import tempfile
import re
from collections import defaultdict
from contextlib import redirect_stdout
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zipfile import ZipFile
from xml.etree import ElementTree as ET

import numpy as np
import altair as alt
import pandas as pd
import streamlit as st

# Configuração de Paths do Sistema
ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# Tentativa de importação do motor da simulação
try:
    from simulador_aquicola import carregar_csv, executar, preparar_curvas
except ImportError:
    st.error("Erro Crítico: Módulo 'simulador_aquicola' não encontrado. Verifique a estrutura do projeto.")
    st.stop()

# Constantes da Aplicação
APP_TITLE = "Simulador de Planejamento Aquícola - Mar & Terra"
DEFAULT_OUTPUT = "simulacao_completa_br.csv"
BRAND_GREEN = "#17413B"
BRAND_GOLD = "#BC933F"
LOGO_WHITE = ROOT_DIR / "app" / "assets" / "mar-terra-logo-branca.png"
LOGO_BLACK = ROOT_DIR / "app" / "assets" / "mar-terra-logo-preta.png"
REQUIRED_FILES = {
    "plantel": "plantel.csv",
    "tanques": "tanques.csv",
    "curvas": "curvas.csv",
    "racao": "racao.csv",
}
PARAMETROS_FILE = "parametros_gerenciais.csv"


def timestamped_filename(file_name: str, momento: datetime | None = None) -> str:
    momento = momento or datetime.now()
    path = Path(file_name)
    return f"{path.stem}_{momento.strftime('%Y%m%d_%H%M%S')}{path.suffix}"

# ==========================================
# DEFINIÇÕES DE TIPOS E DATA CLASSES
# ==========================================

@dataclass(frozen=True)
class SimulationConfig:
    input_dir: Path
    plantel: str
    tanques: str
    curvas: str
    racao: str
    output: str
    data_relatorio: date
    mostrar_erros: bool

@dataclass(frozen=True)
class ReportArtifact:
    file_name: str
    output_bytes: bytes
    captured_output: str = ""
    output_path: str | None = None

# ==========================================
# CONFIGURAÇÃO DE UI (TEMA E CSS)
# ==========================================

def image_data_uri(path: Path) -> str:
    """Converte uma imagem local para Base64 URI para uso no HTML."""
    try:
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        return f"data:image/png;base64,{encoded}"
    except Exception:
        return ""

def configure_page() -> None:
    st.set_page_config(
        page_title="Simulador Aquícola",
        page_icon=str(LOGO_WHITE) if LOGO_WHITE.exists() else "🐟",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.markdown(
        """
        <style>
        :root {
            --brand-green: #17413B;
            --brand-gold: #BC933F;
            --brand-gold-soft: #E7D8B5;
        }
        .main .block-container { padding-top: 1.4rem; max-width: 1180px; }
        .hero {
            display: flex; align-items: center; gap: 1.35rem;
            padding: 1.4rem 1.55rem; border: 1px solid rgba(188, 147, 63, .34);
            border-radius: 10px; background: #17413B;
            margin-bottom: 1.25rem; box-shadow: 0 10px 26px rgba(23, 65, 59, .12);
        }
        .hero-logo { width: min(210px, 34vw); height: auto; flex: 0 0 auto; }
        .hero h1 { margin: 0 0 .35rem 0; font-size: clamp(1.55rem, 3vw, 2.15rem); color: #FFFFFF !important; }
        .hero p { margin: 0; color: #E7D8B5 !important; font-size: 1rem; max-width: 760px; }
        .stButton > button { background: #17413B; color: #FFFFFF; border-color: #BC933F; font-weight: bold; }
        .stButton > button:hover { background: #102F2B; border-color: #A97F2E; color: #FFFFFF; }
        .stDownloadButton > button { width: 100%; background: #17413B; border-color: #BC933F; color: #FFFFFF; }
        </style>
        """,
        unsafe_allow_html=True,
    )

def render_header() -> None:
    logo_markup = f'<img class="hero-logo" src="{image_data_uri(LOGO_WHITE)}" alt="Mar & Terra">' if LOGO_WHITE.exists() else ""
    st.markdown(
        f"""
        <div class="hero">
            {logo_markup}
            <div>
                <h1 style="color:#FFFFFF !important;">{APP_TITLE}</h1>
                <p style="color:#E7D8B5 !important;">
                    Projeção avançada de crescimento, biomassa, consumo e gestão tática regional de abates.
                </p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

# ==========================================
# PROCESSAMENTO NATIVO PANDAS (RACIOCÍNIO ESTENDIDO)
# ==========================================

@st.cache_data(show_spinner=False)
def clean_and_prepare_dataframe(csv_bytes: bytes) -> pd.DataFrame:
    """
    Motor Pandas de Alta Performance.
    Lê o CSV, padroniza as colunas e limpa os dados numéricos/datas via vetorização.
    """
    try:
        # Lê o CSV ignorando linhas mal formatadas
        df = pd.read_csv(io.BytesIO(csv_bytes), sep=';', encoding='utf-8-sig', low_memory=False, on_bad_lines='skip')
        
        # Padronização agressiva de nomes de colunas
        df.columns = df.columns.str.strip().str.lower()
        col_mapping = {
            'região': 'regiao',
            'peso médio (g)': 'peso_medio_g',
            'peso medio (g)': 'peso_medio_g',
            'biomassa (kg)': 'biomassa_kg',
            'biomassa': 'biomassa_kg',
            'status': 'status',
            'produtor': 'produtor',
            'tanque': 'tanque',
            'classe': 'classe',
            'data': 'data',
            'consumo de racao diario (kg)': 'consumo_racao_diario_kg',
            'consumo de ração diario (kg)': 'consumo_racao_diario_kg',
            'consumo de racao acumulado (kg)': 'consumo_racao_acumulado_kg',
            'consumo de ração acumulado (kg)': 'consumo_racao_acumulado_kg',
            'mortalidade acumulada (peixes)': 'mortalidade_acumulada_peixes',
            'mortalidade diaria (peixes)': 'mortalidade_diaria_peixes',
            'tanques disponivel': 'tanques_disponivel',
            'tanques disponíveis': 'tanques_disponivel',
            'tanques liberados': 'tanques_liberados',
        }
        df.rename(columns=col_mapping, inplace=True)
        
        # Se colunas vitais faltarem, retorna df vazio para não quebrar
        required_cols = ['regiao', 'produtor', 'tanque', 'data', 'biomassa_kg', 'peso_medio_g']
        if not all(col in df.columns for col in required_cols):
            return pd.DataFrame()

        # Limpeza Numérica Vetorizada (Regex) para Moeda BR (Ex: R$ 1.500,00 -> 1500.00)
        df['biomassa_kg'] = df['biomassa_kg'].astype(str).str.replace(r'[R\$\s]', '', regex=True) \
                                             .str.replace('.', '', regex=False) \
                                             .str.replace(',', '.', regex=False)
        df['biomassa_kg'] = pd.to_numeric(df['biomassa_kg'], errors='coerce').fillna(0.0)

        df['peso_medio_g'] = df['peso_medio_g'].astype(str).str.replace(r'[R\$\s]', '', regex=True) \
                                               .str.replace('.', '', regex=False) \
                                               .str.replace(',', '.', regex=False)
        df['peso_medio_g'] = pd.to_numeric(df['peso_medio_g'], errors='coerce').fillna(0.0)

        for numeric_col in [
            'consumo_racao_diario_kg',
            'consumo_racao_acumulado_kg',
            'mortalidade_acumulada_peixes',
            'mortalidade_diaria_peixes',
        ]:
            if numeric_col not in df.columns:
                df[numeric_col] = 0.0
            df[numeric_col] = df[numeric_col].astype(str).str.replace(r'[R\$\s]', '', regex=True) \
                                                   .str.replace('.', '', regex=False) \
                                                   .str.replace(',', '.', regex=False)
            df[numeric_col] = pd.to_numeric(df[numeric_col], errors='coerce').fillna(0.0)

        # Parsing de Data
        df['data'] = pd.to_datetime(df['data'], format='mixed', dayfirst=True, errors='coerce')
        df = df.dropna(subset=['data']) # Remove linhas sem data válida
        df['mes'] = df['data'].dt.strftime('%Y-%m')

        # Limpeza de strings cruciais
        df['status'] = df['status'].astype(str).str.strip().str.lower()
        df['regiao_padrao'] = df['regiao'].astype(str).str.strip().str.upper()
        df['classe_padrao'] = df['classe'].astype(str).str.strip().str.title()
        df['produtor'] = df['produtor'].astype(str).str.strip()

        # Classificação Estrita de Regiões
        df['regiao_calc'] = np.where(df['regiao_padrao'].str.contains('APT|TABOADO'), 'APT',
                            np.where(df['regiao_padrao'].str.contains('ITA|ITAPOR'), 'ITA', 'OUTROS'))

        # Classificação Estrita de Classes
        df['classe_calc'] = np.where(df['classe_padrao'].str.contains('Prop|Próp'), 'Próprio',
                            np.where(df['classe_padrao'].str.contains('Parc'), 'Parceria', 'Integração'))

        for flag_col in ['tanques_disponivel', 'tanques_liberados']:
            if flag_col not in df.columns:
                df[flag_col] = 0
            df[flag_col] = pd.to_numeric(df[flag_col], errors='coerce').fillna(0).astype(int)

        return df
    except Exception as e:
        st.error(f"Falha ao ler dados gerados: {str(e)}")
        return pd.DataFrame()


def meta_col(df_metas: pd.DataFrame, *candidatos: str) -> str:
    for candidato in candidatos:
        if candidato in df_metas.columns:
            return candidato
    raise KeyError(f"Coluna ausente na tabela de metas: {' ou '.join(candidatos)}")


def meta_value(df_metas: pd.DataFrame, mes: str, coluna: str) -> float:
    valores = df_metas.loc[df_metas["Mês"] == mes, coluna].values
    if len(valores) == 0:
        return 0.0
    return float(valores[0] or 0.0)


def normalizar_coluna_app(valor: object) -> str:
    texto = str(valor).strip().lower()
    texto = (
        texto.replace("ã", "a")
        .replace("á", "a")
        .replace("à", "a")
        .replace("â", "a")
        .replace("é", "e")
        .replace("ê", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ô", "o")
        .replace("õ", "o")
        .replace("ú", "u")
        .replace("ç", "c")
    )
    return re.sub(r"[^a-z0-9]+", "_", texto).strip("_")


def default_management_frames(data_inicio: date, num_meses: int = 12) -> tuple[pd.DataFrame, pd.DataFrame]:
    primeiro_mes_relatorio = data_inicio.replace(day=1)
    meses = pd.date_range(primeiro_mes_relatorio, periods=num_meses, freq='MS').strftime("%Y-%m").tolist()
    df_metas = pd.DataFrame({
        "Mês": meses,
        "Dias Abate APT": [21] * num_meses,
        "PO Diário APT (kg)": [90000] * num_meses,
        "Dias Abate ITA": [21] * num_meses,
        "PO Diário ITA (kg)": [45000] * num_meses,
    })
    df_terceiros = pd.DataFrame(columns=["Região Destino", "Classe", "Produtor", "Mês", "Volume (kg)"])
    return df_metas, df_terceiros


def parse_parametros_gerenciais(csv_bytes: bytes, data_inicio: date, num_meses: int = 12) -> tuple[pd.DataFrame, pd.DataFrame]:
    df_metas, df_terceiros = default_management_frames(data_inicio, num_meses)
    if not csv_bytes:
        return df_metas, df_terceiros

    raw = pd.read_csv(io.BytesIO(csv_bytes), sep=';', encoding='utf-8-sig', dtype=str).fillna("")
    raw.rename(columns={col: normalizar_coluna_app(col) for col in raw.columns}, inplace=True)
    if "tipo" not in raw.columns:
        return df_metas, df_terceiros

    metas = raw[raw["tipo"].str.strip().str.lower() == "meta"].copy()
    for _, row in metas.iterrows():
        mes = str(row.get("mes", "")).strip()
        regiao = str(row.get("regiao", "")).strip().upper()
        if mes not in set(df_metas["Mês"]) or regiao not in {"APT", "ITA"}:
            continue
        idx = df_metas["Mês"] == mes
        dias = pd.to_numeric(str(row.get("dias_abate", "")).replace(".", "").replace(",", "."), errors="coerce")
        po = pd.to_numeric(str(row.get("po_diario_kg", "")).replace(".", "").replace(",", "."), errors="coerce")
        if pd.notna(dias):
            df_metas.loc[idx, f"Dias Abate {regiao}"] = float(dias)
        if pd.notna(po):
            df_metas.loc[idx, f"PO Diário {regiao} (kg)"] = float(po)

    transferencias = raw[raw["tipo"].str.strip().str.lower() == "transferencia"].copy()
    rows = []
    for _, row in transferencias.iterrows():
        mes = str(row.get("mes", "")).strip()
        regiao = str(row.get("regiao", "")).strip().upper()
        classe = str(row.get("classe", "")).strip() or "Integração"
        produtor = str(row.get("produtor", "")).strip() or "Transferência"
        volume = pd.to_numeric(str(row.get("volume_kg", "")).replace(".", "").replace(",", "."), errors="coerce")
        if mes in set(df_metas["Mês"]) and regiao in {"APT", "ITA"} and pd.notna(volume):
            rows.append({
                "Região Destino": regiao,
                "Classe": classe,
                "Produtor": produtor,
                "Mês": mes,
                "Volume (kg)": float(volume),
            })
    if rows:
        df_terceiros = pd.DataFrame(rows, columns=["Região Destino", "Classe", "Produtor", "Mês", "Volume (kg)"])
    return df_metas, df_terceiros


def parametros_gerenciais_to_csv(df_metas: pd.DataFrame, df_terceiros: pd.DataFrame) -> bytes:
    rows: list[dict[str, object]] = []
    for _, row in df_metas.iterrows():
        mes = row["Mês"]
        for regiao in ["APT", "ITA"]:
            rows.append({
                "tipo": "meta",
                "mes": mes,
                "regiao": regiao,
                "dias_abate": row.get(f"Dias Abate {regiao}", 0),
                "po_diario_kg": row.get(f"PO Diário {regiao} (kg)", 0),
                "classe": "",
                "produtor": "",
                "volume_kg": "",
            })
    if df_terceiros is not None and not df_terceiros.empty:
        for _, row in df_terceiros.iterrows():
            rows.append({
                "tipo": "transferencia",
                "mes": row.get("Mês", ""),
                "regiao": row.get("Região Destino", ""),
                "dias_abate": "",
                "po_diario_kg": "",
                "classe": row.get("Classe", ""),
                "produtor": row.get("Produtor", ""),
                "volume_kg": row.get("Volume (kg)", 0),
            })
    buffer = io.StringIO()
    pd.DataFrame(rows).to_csv(buffer, sep=';', index=False)
    return buffer.getvalue().encode("utf-8-sig")


@st.cache_data(show_spinner=False)
def process_regional_data(df: pd.DataFrame, region: str, df_metas: pd.DataFrame, df_terceiros: pd.DataFrame) -> pd.DataFrame:
    """
    Processa a lógica de negócio agrupando blocos de abates e construindo 
    a estrutura tabular final exigida pelo layout gerencial.
    """
    if df.empty:
        return pd.DataFrame([{"Conteúdo / Bloco": "Dados insuficientes ou colunas ausentes na simulação."}])

    months = df_metas['Mês'].tolist()

    # 1. Filtro Estratégico: Região e Status de Abate
    df_reg = df[(df['regiao_calc'] == region) & ((df['status'] == 'peixe pronto') | (df['peso_medio_g'] >= 900))]
    
    # 2. Remoção de Duplicatas (Manter apenas o último registro do lote no mês)
    df_reg = df_reg.sort_values('data').drop_duplicates(subset=['produtor', 'tanque', 'mes'], keep='last')

    # 3. Agregação Vetorizada de Biomassa
    if not df_reg.empty:
        df_grouped = df_reg.groupby(['classe_calc', 'produtor', 'mes'])['biomassa_kg'].sum().reset_index()
    else:
        df_grouped = pd.DataFrame(columns=['classe_calc', 'produtor', 'mes', 'biomassa_kg'])

    # 4. Estrutura de Memória Otimizada (Dicionário de Matrizes)
    block_data = defaultdict(lambda: defaultdict(float))
    producers_by_classe = {"Próprio": set(), "Integração": set(), "Parceria": set()}

    # Alimentar dados da simulação
    for _, row in df_grouped.iterrows():
        c, p, m, v = row['classe_calc'], row['produtor'], row['mes'], row['biomassa_kg']
        if m in months:
            block_data[(c, p)][m] += v
            producers_by_classe[c].add(p)

    # Alimentar lançamentos manuais (Terceiros/Transferências)
    if not df_terceiros.empty:
        t_reg = df_terceiros[df_terceiros['Região Destino'] == region]
        for _, row in t_reg.iterrows():
            c, p, m = row['Classe'], row['Produtor'], row['Mês']
            v = pd.to_numeric(row.get('Volume (kg)', 0), errors="coerce")
            if m in months and pd.notna(v):
                block_data[(c, p)][m] += float(v)
                producers_by_classe[c].add(p)

    # ==========================================
    # MONTAGEM DO LAYOUT CORPORATIVO EXCEL
    # ==========================================
    output_rows = []
    totals = {c: {m: 0.0 for m in months} for c in producers_by_classe.keys()}

    # Blocos de Produtores
    for cl in ["Próprio", "Integração", "Parceria"]:
        output_rows.append({"Conteúdo / Bloco": f"QUADRO DE PEIXE GORDO - {cl.upper()} - {region}", **{m: "" for m in months}})
        
        for prod in sorted(list(producers_by_classe[cl])):
            row_dict = {"Conteúdo / Bloco": prod}
            for m in months:
                val = block_data[(cl, prod)][m]
                row_dict[m] = val
                totals[cl][m] += val
            output_rows.append(row_dict)
            
        t_dict = {"Conteúdo / Bloco": f"Total {cl}"}
        for m in months: t_dict[m] = totals[cl][m]
        output_rows.append(t_dict)
        output_rows.append({col: "" for col in ["Conteúdo / Bloco"] + months})

    # Bloco: Totais e Metas
    output_rows.append({"Conteúdo / Bloco": f"QUADRO DE PEIXE GORDO TOTAL - {region}", **{m: "" for m in months}})
    
    prevs = {
        "Previsão de Abate Próprio": totals["Próprio"],
        "Previsão de Abate Integração": totals["Integração"],
        "Previsão de Abate Parceria": totals["Parceria"],
    }
    prev_total = {m: sum(prevs[k][m] for k in prevs) for m in months}
    dias_col = meta_col(df_metas, f"Dias Abate {region}")
    po_col = meta_col(df_metas, f"PO Diário {region} (kg)", f"PO {region} (kg)")
    dias_abate = {m: max(1.0, meta_value(df_metas, m, dias_col)) for m in months}
    po_diario = {m: meta_value(df_metas, m, po_col) for m in months}
    abate_po_mes = {m: po_diario[m] * dias_abate[m] for m in months}

    for label, data_dict in prevs.items():
        output_rows.append({"Conteúdo / Bloco": label, **data_dict})
    output_rows.append({"Conteúdo / Bloco": "Previsão Disponibilidade Total", **prev_total})
    output_rows.append({"Conteúdo / Bloco": "Abate PO Atualizado Total Mês", **abate_po_mes})
    output_rows.append({col: "" for col in ["Conteúdo / Bloco"] + months})

    # Bloco: Disponibilidade por Dia
    output_rows.append({"Conteúdo / Bloco": f"QUADRO DE DISPONIBILIDADE PARA O ABATE POR DIA - {region}", **{m: "" for m in months}})
    
    output_rows.append({"Conteúdo / Bloco": "Dias de Abate", **dias_abate})
    
    kg_dia_total = {m: prev_total[m] / dias_abate[m] for m in months}
    output_rows.append({"Conteúdo / Bloco": "Kg/Dia Próprio", **{m: prevs["Previsão de Abate Próprio"][m] / dias_abate[m] for m in months}})
    output_rows.append({"Conteúdo / Bloco": "Kg/Dia Integração", **{m: prevs["Previsão de Abate Integração"][m] / dias_abate[m] for m in months}})
    output_rows.append({"Conteúdo / Bloco": "Kg/Dia Parceria", **{m: prevs["Previsão de Abate Parceria"][m] / dias_abate[m] for m in months}})
    output_rows.append({"Conteúdo / Bloco": "Total Kg/Dia Disponível Abate", **kg_dia_total})
    output_rows.append({col: "" for col in ["Conteúdo / Bloco"] + months})

    # Bloco: Saldos
    output_rows.append({"Conteúdo / Bloco": f"QUADRO DO SALDO DA DISPONIBILIDADE PARA O ABATE POR DIA e POR MÊS - {region}", **{m: "" for m in months}})
    
    saldo_dia = {m: kg_dia_total[m] - po_diario[m] for m in months}
    
    output_rows.append({"Conteúdo / Bloco": "PO Atualizado", **po_diario})
    output_rows.append({"Conteúdo / Bloco": "Saldo Atualizado / dia", **saldo_dia})
    
    saldo_acm = {}
    running_acm = 0.0
    for m in months:
        running_acm += saldo_dia[m] * dias_abate[m]
        saldo_acm[m] = running_acm
        
    output_rows.append({"Conteúdo / Bloco": "Saldo Acm Atualizado / mês", **saldo_acm})

    return pd.DataFrame(output_rows)


@st.cache_data(show_spinner=False)
def process_consolidated_data(
    df: pd.DataFrame,
    df_apt: pd.DataFrame,
    df_ita: pd.DataFrame,
    df_metas: pd.DataFrame,
) -> pd.DataFrame:
    """Monta a aba consolidada no formato operacional da planilha gerencial."""
    if df.empty:
        return pd.DataFrame([{"Conteúdo / Bloco": "Dados insuficientes ou colunas ausentes na simulação."}])

    months = df_metas['Mês'].tolist()
    output_rows: list[dict[str, object]] = []

    def empty_row() -> dict[str, object]:
        return {col: "" for col in ["Conteúdo / Bloco"] + months}

    def row_values(source: pd.DataFrame, label: str) -> dict[str, float]:
        if source.empty or "Conteúdo / Bloco" not in source.columns:
            return {m: 0.0 for m in months}
        match = source[source["Conteúdo / Bloco"] == label]
        if match.empty:
            return {m: 0.0 for m in months}
        row = match.iloc[0]
        values = {}
        for m in months:
            value = pd.to_numeric(row.get(m, 0.0), errors="coerce")
            values[m] = 0.0 if pd.isna(value) else float(value)
        return values

    def sum_series(*series: dict[str, float]) -> dict[str, float]:
        return {m: sum(item.get(m, 0.0) for item in series) for m in months}

    def diff_series(left: dict[str, float], right: dict[str, float]) -> dict[str, float]:
        return {m: left.get(m, 0.0) - right.get(m, 0.0) for m in months}

    def multiply_series(left: dict[str, float], right: dict[str, float]) -> dict[str, float]:
        return {m: left.get(m, 0.0) * right.get(m, 0.0) for m in months}

    def weighted_avg_weight(region: str) -> dict[str, float]:
        ready = df[
            (df['regiao_calc'] == region)
            & ((df['status'] == 'peixe pronto') | (df['peso_medio_g'] >= 900))
        ].sort_values('data').drop_duplicates(
            subset=['produtor', 'tanque', 'mes'],
            keep='last',
        )
        if ready.empty:
            return {m: 0.0 for m in months}
        grouped = ready.groupby('mes').apply(
            lambda data: np.average(
                data['peso_medio_g'],
                weights=np.maximum(data['biomassa_kg'], 1),
            )
        ).to_dict()
        return {m: float(grouped.get(m, 0.0)) for m in months}

    apt = {
        "dias": row_values(df_apt, "Dias de Abate"),
        "kg_proprio": row_values(df_apt, "Kg/Dia Próprio"),
        "kg_integracao": row_values(df_apt, "Kg/Dia Integração"),
        "kg_parceria": row_values(df_apt, "Kg/Dia Parceria"),
        "total_dia": row_values(df_apt, "Total Kg/Dia Disponível Abate"),
        "po": row_values(df_apt, "PO Atualizado"),
        "saldo_dia": row_values(df_apt, "Saldo Atualizado / dia"),
        "saldo_acm": row_values(df_apt, "Saldo Acm Atualizado / mês"),
        "total_mes": row_values(df_apt, "Previsão Disponibilidade Total"),
        "peso_medio": weighted_avg_weight("APT"),
    }
    ita = {
        "dias": row_values(df_ita, "Dias de Abate"),
        "kg_proprio": row_values(df_ita, "Kg/Dia Próprio"),
        "kg_integracao": row_values(df_ita, "Kg/Dia Integração"),
        "kg_parceria": row_values(df_ita, "Kg/Dia Parceria"),
        "total_dia": row_values(df_ita, "Total Kg/Dia Disponível Abate"),
        "po": row_values(df_ita, "PO Atualizado"),
        "saldo_dia": row_values(df_ita, "Saldo Atualizado / dia"),
        "saldo_acm": row_values(df_ita, "Saldo Acm Atualizado / mês"),
        "total_mes": row_values(df_ita, "Previsão Disponibilidade Total"),
        "peso_medio": weighted_avg_weight("ITA"),
    }

    def regional_block(region_name: str, title: str, data: dict[str, dict[str, float]]) -> None:
        output_rows.append({"Conteúdo / Bloco": region_name, **{m: title for m in months}})
        output_rows.append({"Conteúdo / Bloco": "Dias de Abate", **data["dias"]})
        output_rows.append({"Conteúdo / Bloco": "Kg/Dia Próprio", **data["kg_proprio"]})
        output_rows.append({"Conteúdo / Bloco": "Kg/Dia Integração", **data["kg_integracao"]})
        output_rows.append({"Conteúdo / Bloco": "Kg/Dia Parceria", **data["kg_parceria"]})
        output_rows.append({"Conteúdo / Bloco": "Total Kg/Dia Dispon Abate", **data["total_dia"]})
        output_rows.append({"Conteúdo / Bloco": "PO Atualizado", **data["po"]})
        output_rows.append({"Conteúdo / Bloco": "PO", **data["po"]})
        output_rows.append({
            "Conteúdo / Bloco": "Saldo PO Atual. x Disponível",
            **multiply_series(data["saldo_dia"], data["dias"]),
        })
        output_rows.append({"Conteúdo / Bloco": "Peso Médio", **data["peso_medio"]})
        output_rows.append(empty_row())

    regional_block("APT", "QUADRO DE DISPONIBILIDADE PARA O ABATE / DIA - APT", apt)
    regional_block("ITAPORÃ", "QUADRO DE DISPONIBILIDADE DE BIOMASSA PARA O ABATE POR DIA - ITA", ita)

    geral_total_dia = sum_series(apt["total_dia"], ita["total_dia"])
    geral_po = sum_series(apt["po"], ita["po"])
    geral_saldo_dia = diff_series(geral_total_dia, geral_po)
    geral_total_mes = sum_series(apt["total_mes"], ita["total_mes"])
    geral_abate_po_mes = sum_series(
        multiply_series(apt["po"], apt["dias"]),
        multiply_series(ita["po"], ita["dias"]),
    )
    geral_saldo_mes = diff_series(geral_total_mes, geral_abate_po_mes)
    geral_saldo_acm = sum_series(apt["saldo_acm"], ita["saldo_acm"])

    output_rows.append({"Conteúdo / Bloco": "QUADRO DE DISPONIBILIDADE PARA O ABATE / DIA - GERAL", **{m: "" for m in months}})
    output_rows.append({"Conteúdo / Bloco": "Total Kg/Dia Disponível Abate", **geral_total_dia})
    output_rows.append({"Conteúdo / Bloco": "PO Atualizado", **geral_po})
    output_rows.append({"Conteúdo / Bloco": "PO", **geral_po})
    output_rows.append({"Conteúdo / Bloco": "Saldo PO Atualizado", **geral_saldo_dia})
    output_rows.append({"Conteúdo / Bloco": "Saldo PO", **geral_saldo_dia})
    output_rows.append(empty_row())

    output_rows.append({"Conteúdo / Bloco": "QUADRO DE DISPONIBILIDADE PARA O ABATE / MÊS - GERAL", **{m: "" for m in months}})
    output_rows.append({"Conteúdo / Bloco": "Total Kg/Mês Disponível Abate", **geral_total_mes})
    output_rows.append({"Conteúdo / Bloco": "PO Atualizado (No mês) Saldo", **geral_saldo_mes})
    output_rows.append({"Conteúdo / Bloco": "Saldo PO Atual. x Disponível", **geral_saldo_mes})
    output_rows.append({"Conteúdo / Bloco": "Saldo Acm Atualizado / mês", **geral_saldo_acm})

    return pd.DataFrame(output_rows)


def build_next_generation_plantel(csv_bytes: bytes) -> bytes:
    df = clean_and_prepare_dataframe(csv_bytes)
    if df.empty or 'tanques_disponivel' not in df.columns:
        return b""
    disponiveis = df[df['tanques_disponivel'] == 1].sort_values('data')
    if disponiveis.empty:
        output = pd.DataFrame(
            columns=[
                "Produtor",
                "Tanque",
                "Data Entrada",
                "Saldo Final",
                "Dt.últ Biometria",
                "Última Pesagem(g)",
                "Região",
                "Classe",
                "Status Planejamento",
            ]
        )
    else:
        latest = disponiveis.drop_duplicates(subset=['tanque'], keep='first')
        output = pd.DataFrame(
            {
                "Produtor": "",
                "Tanque": latest['tanque'],
                "Data Entrada": latest['data'].dt.strftime("%d/%m/%Y"),
                "Saldo Final": 0,
                "Dt.últ Biometria": latest['data'].dt.strftime("%d/%m/%Y"),
                "Última Pesagem(g)": 0,
                "Região": latest['regiao'],
                "Classe": latest['classe'],
                "Status Planejamento": "Disponivel para novo povoamento",
            }
        )
    buffer = io.StringIO()
    output.to_csv(buffer, sep=';', index=False)
    return buffer.getvalue().encode('utf-8-sig')

# ==========================================
# UTILITÁRIOS DE UI E EXPORTAÇÃO
# ==========================================

def format_br_number(value: Any, decimals: int = 2) -> str:
    """Formatações precisas para visualização do usuário."""
    if pd.isna(value) or value == "":
        return ""
    try:
        val = float(value)
        formatted = f"{val:,.{decimals}f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return formatted
    except (ValueError, TypeError):
        return str(value)

def format_df_for_display(df: pd.DataFrame) -> pd.DataFrame:
    """Aplica máscara visual inteira em DataFrames sem alterar a base de cálculo."""
    display_df = df.copy()
    for col in display_df.columns:
        if col == "Conteúdo / Bloco": continue
        
        formatted_col = []
        for _, row in display_df.iterrows():
            v = row[col]
            lbl = str(row["Conteúdo / Bloco"])
            
            if pd.isna(v) or v == "":
                formatted_col.append("")
            else:
                formatted_col.append(format_br_number(v, 0))
                
        display_df[col] = formatted_col
    return display_df


def dataframe_for_chart(df: pd.DataFrame, labels: list[str]) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    chart_rows = df[df["Conteúdo / Bloco"].isin(labels)]
    if chart_rows.empty:
        return pd.DataFrame()
    chart_df = chart_rows.set_index("Conteúdo / Bloco").T
    return chart_df.apply(pd.to_numeric, errors="coerce").fillna(0.0)


def ultimo_valor_relevante(serie: pd.Series) -> float:
    """Retorna o último valor não zerado da série, ou 0 se toda a série estiver vazia."""
    valores = pd.to_numeric(serie, errors="coerce").fillna(0.0)
    valores = valores[valores != 0]
    if valores.empty:
        return 0.0
    return float(valores.iloc[-1])


def render_line_chart(chart_df: pd.DataFrame, title: str, y_title: str) -> None:
    """Renderiza gráficos com eixos explícitos para evitar leituras ambíguas."""
    if chart_df.empty:
        return

    chart_data = (
        chart_df.reset_index(names="Mês")
        .melt(id_vars="Mês", var_name="Indicador", value_name="Valor")
    )
    chart = (
        alt.Chart(chart_data)
        .mark_line(point=True, strokeWidth=2.5)
        .encode(
            x=alt.X("Mês:N", title="Mês", sort=None),
            y=alt.Y("Valor:Q", title=y_title),
            color=alt.Color(
                "Indicador:N",
                title="Indicador",
                scale=alt.Scale(range=[BRAND_GREEN, BRAND_GOLD, "#5F6B7A"]),
                legend=alt.Legend(orient="left"),
            ),
            tooltip=[
                alt.Tooltip("Mês:N", title="Mês"),
                alt.Tooltip("Indicador:N", title="Indicador"),
                alt.Tooltip("Valor:Q", title="Valor", format=",.2f"),
            ],
        )
        .properties(title=title, height=320)
        .configure_title(anchor="start", fontSize=16, fontWeight="bold")
        .configure_axis(labelFontSize=12, titleFontSize=13)
        .configure_legend(labelFontSize=12, titleFontSize=12)
    )
    st.altair_chart(chart, use_container_width=True)


def styled_report_dataframe(df: pd.DataFrame) -> pd.io.formats.style.Styler:
    """Aplica alternância de linhas e destaque visual com contraste WCAG."""

    def row_style(row: pd.Series) -> list[str]:
        label = str(row.get("Conteúdo / Bloco", "")).lower()
        size = len(row)

        if not label.strip():
            return ["background-color: transparent;"] * size
        if "próprio" in label or "proprio" in label:
            return [
                "background-color: #D9EAF7; color: #0F3048; font-weight: 800;"
            ] * size
        if "integração" in label or "integracao" in label:
            return [
                "background-color: #F6E0BF; color: #5C3300; font-weight: 800;"
            ] * size
        if "parceria" in label:
            return [
                "background-color: #DCEFE2; color: #17413B; font-weight: 800;"
            ] * size
        if label == "dias de abate":
            return [
                "background-color: #F1D6D6; color: #5A1515; font-weight: 900;"
            ] * size
        if "quadro" in label:
            return [
                "background-color: #76581E; color: #FFFFFF; font-weight: 800;"
            ] * size
        if label in {"apt", "itaporã", "itapora"}:
            return [
                "background-color: #66706E; color: #FFFFFF; font-weight: 800;"
            ] * size
        if "previsão disponibilidade total" in label or "previsao disponibilidade total" in label:
            return [
                "background-color: #5E6F6B; color: #FFFFFF; font-weight: 900;"
            ] * size
        if "abate po atualizado total" in label:
            return [
                "background-color: #E7D8B5; color: #17413B; font-weight: 900;"
            ] * size
        if "total" in label:
            return [
                "background-color: #66706E; color: #FFFFFF; font-weight: 800;"
            ] * size
        if "saldo" in label:
            return [
                "background-color: #F3E6C8; color: #17413B; font-weight: 800;"
            ] * size
        if label in {"po", "po atualizado"} or "po atualizado" in label:
            return [
                "background-color: #E7D8B5; color: #17413B; font-weight: 800;"
            ] * size
        if any(marker in label for marker in ["biometria", "liberado", "disponivel", "disponível"]):
            return [
                "background-color: #E7D8B5; color: #17413B; font-weight: 800;"
            ] * size
        if isinstance(row.name, int) and row.name % 2 == 0:
            return ["background-color: #F7F7F7; color: #111827;"] * size
        return ["background-color: #FFFFFF; color: #111827;"] * size

    return (
        df.style.apply(row_style, axis=1)
        .set_properties(
            subset=["Conteúdo / Bloco"],
            **{
                "min-width": "300px",
                "max-width": "420px",
                "white-space": "normal",
                "font-weight": "700",
            },
        )
        .set_table_styles(
            [
                {
                    "selector": "th",
                    "props": [
                        ("background-color", "#17413B"),
                        ("color", "#FFFFFF"),
                        ("font-weight", "800"),
                        ("border-color", "#BC933F"),
                    ],
                }
            ]
        )
        .hide(axis="index")
    )


def audit_xlsx_formulas(xlsx_bytes: bytes) -> pd.DataFrame:
    """Inspeciona fórmulas de um XLSX e aponta erros prováveis de arrasto/referência."""
    issues: list[dict[str, str]] = []
    ns = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with ZipFile(io.BytesIO(xlsx_bytes)) as archive:
        sheet_files = [
            name for name in archive.namelist()
            if name.startswith("xl/worksheets/sheet") and name.endswith(".xml")
        ]
        for sheet_name in sheet_files:
            root = ET.fromstring(archive.read(sheet_name))
            for cell in root.findall(".//a:c", ns):
                formula = cell.find("a:f", ns)
                if formula is None or not formula.text:
                    continue
                cell_ref = cell.attrib.get("r", "")
                formula_text = formula.text
                problem = ""
                if "#REF!" in formula_text.upper():
                    problem = "Referência quebrada (#REF!)"
                elif cell_ref and re.search(rf"(?<![A-Z0-9]){re.escape(cell_ref)}(?![A-Z0-9])", formula_text, re.I):
                    problem = "Possível referência circular direta"
                elif re.search(r":\s*$|,\s*$|;\s*$", formula_text):
                    problem = "Fórmula possivelmente incompleta"
                if problem:
                    issues.append(
                        {
                            "Planilha XML": sheet_name,
                            "Célula": cell_ref,
                            "Problema": problem,
                            "Fórmula": formula_text,
                        }
                    )
    return pd.DataFrame(issues)


def export_to_excel(df_apt: pd.DataFrame, df_ita: pd.DataFrame, df_consolidado: pd.DataFrame) -> bytes:
    """Gera o binário Excel com múltiplas abas."""
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df_apt.to_excel(writer, sheet_name="APT", index=False)
        df_ita.to_excel(writer, sheet_name="ITA", index=False)
        df_consolidado.to_excel(writer, sheet_name="Consolidado APT + ITA", index=False)
    return buffer.getvalue()

# ==========================================
# CONTROLES INTERATIVOS DO STREAMLIT
# ==========================================

def render_management_inputs(
    data_inicio: date,
    num_meses: int = 12,
    parametros_bytes: bytes | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    st.divider()
    st.subheader("📊 Parâmetros Gerenciais e Metas")
    st.caption("Insira e ajuste as metas comerciais, dias operacionais e volumes extras antes de simular.")
    
    df_metas_base, df_terceiros_base = parse_parametros_gerenciais(parametros_bytes or b"", data_inicio, num_meses)
    meses = df_metas_base["Mês"].tolist()
        
    col1, col2 = st.columns([1.1, 0.9])
    
    with col1:
        st.markdown("#### 1. Metas (PO) e Dias de Abate por Região")
        df_metas_editado = st.data_editor(
            df_metas_base,
            use_container_width=True,
            hide_index=True,
            key=f"metas_editor_{data_inicio.isoformat()}_{hash(parametros_bytes)}",
            column_config={
                "Mês": st.column_config.TextColumn("Mês", disabled=True),
                "Dias Abate APT": st.column_config.NumberColumn("Dias Abate APT", min_value=1, step=1),
                "PO Diário APT (kg)": st.column_config.NumberColumn("PO Diário APT (kg)", min_value=0, step=1000),
                "Dias Abate ITA": st.column_config.NumberColumn("Dias Abate ITA", min_value=1, step=1),
                "PO Diário ITA (kg)": st.column_config.NumberColumn("PO Diário ITA (kg)", min_value=0, step=1000),
            },
        )

    with col2:
        st.markdown("#### 2. Volumes de Terceiros e Transferências")
        df_terceiros_editado = st.data_editor(
            df_terceiros_base,
            num_rows="dynamic",
            use_container_width=True,
            hide_index=True,
            column_config={
                "Região Destino": st.column_config.SelectboxColumn("Região Destino", options=["APT", "ITA"], required=True),
                "Classe": st.column_config.SelectboxColumn("Classe", options=["Próprio", "Integração", "Parceria"], required=True),
                "Mês": st.column_config.SelectboxColumn("Mês", options=meses, required=True),
                "Volume (kg)": st.column_config.NumberColumn("Volume (kg)", required=True, step=1000.0),
                "Produtor": st.column_config.TextColumn("Produtor", required=True)
            },
            key=f"terceiros_editor_{data_inicio.isoformat()}_{hash(parametros_bytes)}"
        )

    meses_visiveis = st.multiselect(
        "Meses exibidos no relatório da tela",
        options=meses,
        default=meses,
        help="Filtra dinamicamente as tabelas e gráficos das abas APT, ITA e Consolidado.",
    )
    if not meses_visiveis:
        meses_visiveis = meses

    parametros_csv = parametros_gerenciais_to_csv(df_metas_editado, df_terceiros_editado)
    st.download_button(
        "📥 Baixar parâmetros gerenciais atualizados",
        data=parametros_csv,
        file_name=PARAMETROS_FILE,
        mime="text/csv",
        use_container_width=True,
        key="download_parametros_gerenciais",
    )

    return df_metas_editado, df_terceiros_editado, meses_visiveis


def render_spreadsheet_audit() -> None:
    with st.expander("Auditoria opcional da planilha base"):
        st.caption("Verifica fórmulas com #REF!, possíveis referências circulares diretas e fórmulas incompletas.")
        workbook = st.file_uploader(
            "Planilha base de projeção (.xlsx)",
            type=["xlsx"],
            key="audit_workbook_upload",
        )
        if workbook is None:
            return
        try:
            issues = audit_xlsx_formulas(workbook.getvalue())
        except Exception as exc:
            st.error(f"Não foi possível auditar a planilha: {exc}")
            return
        if issues.empty:
            st.success("Nenhum problema evidente encontrado nas fórmulas auditadas.")
        else:
            st.warning(f"Foram encontrados {len(issues)} ponto(s) para revisão.")
            st.dataframe(issues, use_container_width=True, hide_index=True)


def curvas_cluster_dataframe_from_path(path: Path) -> pd.DataFrame:
    curvas = preparar_curvas(carregar_csv(path))
    rows = []
    for curva in curvas:
        cluster = str(curva.get("cluster", "") or "Curva padrão").strip() or "Curva padrão"
        rows.append(
            {
                "Dia": int(curva["dia"]),
                "Estação": "Verão" if curva["estacao"] == "V" else "Inverno",
                "Cluster": cluster,
                "Peso Médio (g)": float(curva["peso_ref_g"]),
                "GDP (g/dia)": float(curva["gdp_g"]),
                "Mortalidade (%)": float(curva["mortalidade_pct"]),
            }
        )
    return pd.DataFrame(rows)


def curvas_cluster_dataframe_from_bytes(csv_bytes: bytes) -> pd.DataFrame:
    with tempfile.TemporaryDirectory() as temp_dir:
        path = Path(temp_dir) / "curvas.csv"
        path.write_bytes(csv_bytes)
        return curvas_cluster_dataframe_from_path(path)


def render_curve_programs_preview(curvas_df: pd.DataFrame) -> None:
    if curvas_df.empty or curvas_df["Cluster"].nunique() <= 1:
        return

    with st.expander("Comparativo de programas / curvas por cluster", expanded=False):
        metric = st.radio(
            "Métrica da curva",
            ["Peso Médio (g)", "GDP (g/dia)", "Mortalidade (%)"],
            horizontal=True,
            key="curvas_cluster_metric",
        )
        chart = (
            alt.Chart(curvas_df)
            .mark_line(point=False, strokeWidth=2)
            .encode(
                x=alt.X("Dia:Q", title="Dia de cultivo"),
                y=alt.Y(f"{metric}:Q", title=metric),
                color=alt.Color("Cluster:N", title="Programa / Cluster", legend=alt.Legend(orient="left")),
                strokeDash=alt.StrokeDash("Estação:N", title="Estação"),
                tooltip=["Dia:Q", "Estação:N", "Cluster:N", alt.Tooltip(f"{metric}:Q", title=metric, format=",.2f")],
            )
            .properties(height=320)
        )
        st.altair_chart(chart, use_container_width=True)

# ==========================================
# GERAÇÃO DO DASHBOARD E INTERFACE PRINCIPAL
# ==========================================

def render_excel_style_view(csv_bytes: bytes) -> None:
    st.subheader("📋 Relatório Corporativo de Projeção de Abate")
    st.caption("Visões estruturadas por blocos e regiões (Idêntico ao modelo Excel de controle).")
    
    df_metas = st.session_state.get("df_metas")
    df_terceiros = st.session_state.get("df_terceiros")
    meses_visiveis = st.session_state.get("meses_visiveis")
    
    if df_metas is None:
        st.warning("Preencha as configurações de parâmetros gerenciais no topo da página.")
        return
    if meses_visiveis:
        df_metas = df_metas[df_metas["Mês"].isin(meses_visiveis)].copy()
        if df_terceiros is not None and not df_terceiros.empty:
            df_terceiros = df_terceiros[df_terceiros["Mês"].isin(meses_visiveis)].copy()
        
    with st.spinner("Processando base de dados com Pandas..."):
        df_base = clean_and_prepare_dataframe(csv_bytes)
        
        if df_base.empty:
            st.error("Falha ao analisar a base de dados. Verifique a estrutura do CSV gerado.")
            return

        df_apt_raw = process_regional_data(df_base, "APT", df_metas, df_terceiros)
        df_ita_raw = process_regional_data(df_base, "ITA", df_metas, df_terceiros)
        df_consolidado_raw = process_consolidated_data(df_base, df_apt_raw, df_ita_raw, df_metas)
    
    excel_bytes = export_to_excel(df_apt_raw, df_ita_raw, df_consolidado_raw)
    
    st.download_button(
        label="📥 Baixar Relatório Gerencial em Excel (.xlsx)",
        data=excel_bytes,
        file_name=timestamped_filename("Projeção_Abate_Geral_Gerado.xlsx"),
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )
    plantel_bytes = build_next_generation_plantel(csv_bytes)
    if plantel_bytes:
        st.download_button(
            label="📥 Baixar Plantel para Nova Geração (.csv)",
            data=plantel_bytes,
            file_name=timestamped_filename("plantel_nova_geracao.csv"),
            mime="text/csv",
            use_container_width=True,
        )
    
    tab_apt, tab_ita, tab_consolidado = st.tabs(
        ["Aba APT (Aparecida do Taboado)", "Aba ITA (Itaporã)", "Consolidado APT + ITA"]
    )
    with tab_apt:
        chart_apt = dataframe_for_chart(
            df_apt_raw,
            ["Previsão Disponibilidade Total", "Abate PO Atualizado Total Mês"],
        )
        if not chart_apt.empty:
            render_line_chart(chart_apt, "APT - Biomassa disponível x PO mensal", "Biomassa / abate projetado (kg)")
        st.dataframe(styled_report_dataframe(format_df_for_display(df_apt_raw)), use_container_width=True, height=550)
    with tab_ita:
        chart_ita = dataframe_for_chart(
            df_ita_raw,
            ["Previsão Disponibilidade Total", "Abate PO Atualizado Total Mês"],
        )
        if not chart_ita.empty:
            render_line_chart(chart_ita, "ITA - Biomassa disponível x PO mensal", "Biomassa / abate projetado (kg)")
        st.dataframe(styled_report_dataframe(format_df_for_display(df_ita_raw)), use_container_width=True, height=550)
    with tab_consolidado:
        chart_consolidado = dataframe_for_chart(
            df_consolidado_raw,
            [
                "Total Kg/Mês Disponível Abate",
                "PO Atualizado (No mês) Saldo",
                "Saldo Acm Atualizado / mês",
            ],
        )
        if not chart_consolidado.empty:
            metric_cols = st.columns(3)
            for col, label in zip(metric_cols, chart_consolidado.columns[:3]):
                col.metric(label, format_br_number(ultimo_valor_relevante(chart_consolidado[label]), 0))
            render_line_chart(chart_consolidado, "Consolidado APT + ITA", "Valor consolidado")
        st.dataframe(styled_report_dataframe(format_df_for_display(df_consolidado_raw)), use_container_width=True, height=720)

def render_common_settings() -> tuple[date, str, bool]:
    st.subheader("Configurações da simulação")
    col1, col2, col3 = st.columns([1, 1.3, 1])
    with col1:
        data_relatorio = st.date_input("Data do relatório", value=date.today(), format="DD/MM/YYYY")
    with col2:
        raw_output = st.text_input("Arquivo de saída", value=DEFAULT_OUTPUT)
        output_name = raw_output if raw_output.lower().endswith(".csv") else f"{raw_output}.csv"
    with col3:
        mostrar_erros = st.checkbox("Mostrar erros de inconsistência", value=False)
    return data_relatorio, output_name, mostrar_erros


def resolve_output_path(output_name: str) -> Path:
    output_path = Path(output_name).expanduser()
    if output_path.is_absolute() or output_path.parent != Path("."):
        return output_path
    return ROOT_DIR / "data" / "output" / output_path.name


def run_simulation(config: SimulationConfig) -> tuple[Path, str]:
    stdout_buffer = io.StringIO()
    output_path = resolve_output_path(config.output)
    args = argparse.Namespace(
        input_dir=str(config.input_dir), plantel=config.plantel,
        tanques=config.tanques, curvas=config.curvas, racao=config.racao,
        output=str(output_path), mostrar_erros=config.mostrar_erros,
        data_relatorio=config.data_relatorio.strftime("%d/%m/%Y"),
    )
    with redirect_stdout(stdout_buffer):
        output_path = executar(args)
    return Path(output_path), stdout_buffer.getvalue().strip()

def main() -> None:
    configure_page()
    render_header()

    with st.sidebar:
        if LOGO_BLACK.exists(): st.image(str(LOGO_BLACK), use_container_width=True)
        st.header("Fluxo de Trabalho")
        st.markdown(
            """
            1. Ajuste **Metas e Lançamentos** Manuais.
            2. Insira os CSVs de base.
            3. Clique em **Executar Simulação**.
            4. Baixe o relatório consolidado pronto para diretoria.
            """
        )

    data_relatorio, output_name, mostrar_erros = render_common_settings()

    # Controles Interativos (Salvos no Session State)
    with st.expander("Arquivo opcional de parâmetros gerenciais", expanded=False):
        parametros_upload = st.file_uploader(
            "parametros_gerenciais.csv",
            type=["csv"],
            key="u_parametros_gerenciais",
            help="Opcional. Se enviado, preenche as tabelas de metas, dias de abate e transferências.",
        )
        parametros_bytes = parametros_upload.getvalue() if parametros_upload is not None else None

    df_metas, df_terceiros, meses_visiveis = render_management_inputs(
        data_relatorio,
        num_meses=12,
        parametros_bytes=parametros_bytes,
    )
    st.session_state["df_metas"] = df_metas
    st.session_state["df_terceiros"] = df_terceiros
    st.session_state["meses_visiveis"] = meses_visiveis
    render_spreadsheet_audit()

    tab_upload, tab_path = st.tabs(["📤 Upload de Arquivos", "📁 Execução Local"])
    
    uploaded_files = {}
    with tab_upload:
        col1, col2 = st.columns(2)
        with col1:
            uploaded_files["plantel"] = st.file_uploader("plantel.csv", type=["csv"], key="u_plantel")
            uploaded_files["curvas"] = st.file_uploader("curvas.csv", type=["csv"], key="u_curvas")
        with col2:
            uploaded_files["tanques"] = st.file_uploader("tanques.csv", type=["csv"], key="u_tanques")
            uploaded_files["racao"] = st.file_uploader("racao.csv", type=["csv"], key="u_racao")

        if uploaded_files.get("curvas") is not None:
            try:
                render_curve_programs_preview(
                    curvas_cluster_dataframe_from_bytes(uploaded_files["curvas"].getvalue())
                )
            except Exception as exc:
                st.info(f"Não foi possível montar o comparativo de curvas: {exc}")
            
        missing = [f for k, f in REQUIRED_FILES.items() if uploaded_files.get(k) is None]
        if missing:
            st.warning("Envie todos os arquivos obrigatórios: " + ", ".join(missing))
            st.button("🚀 Executar Simulação", disabled=True, key="btn_up_disabled")
        else:
            if st.button("🚀 Executar Simulação", type="primary", key="btn_up_run"):
                try:
                    with tempfile.TemporaryDirectory() as temp_dir:
                        work_dir = Path(temp_dir)
                        for key, file_name in REQUIRED_FILES.items():
                            (work_dir / file_name).write_bytes(uploaded_files[key].getbuffer())
                            
                        config = SimulationConfig(
                            input_dir=work_dir, plantel=REQUIRED_FILES["plantel"],
                            tanques=REQUIRED_FILES["tanques"], curvas=REQUIRED_FILES["curvas"],
                            racao=REQUIRED_FILES["racao"], output=output_name,
                            data_relatorio=data_relatorio, mostrar_erros=mostrar_erros,
                        )
                        with st.spinner("Motor de Cálculo em Execução..."):
                            out_path, stdout = run_simulation(config)
                            out_bytes = out_path.read_bytes()
                            
                    st.session_state["last_artifact"] = ReportArtifact(out_path.name, out_bytes, stdout, str(out_path))
                except Exception as e:
                    st.error(f"Falha Crítica na Execução: {e}")

    with tab_path:
        st.caption("Modo desenvolvedor: leitura direta do diretório local.")
        input_dir = Path(st.text_input("Pasta 'input'", value=str(ROOT_DIR / "data" / "input"))).expanduser()
        curvas_local = input_dir / REQUIRED_FILES["curvas"]
        if curvas_local.exists():
            try:
                render_curve_programs_preview(curvas_cluster_dataframe_from_path(curvas_local))
            except Exception as exc:
                st.info(f"Não foi possível montar o comparativo de curvas local: {exc}")
        
        if st.button("🚀 Executar Simulação Local", type="primary", key="btn_local_run"):
            config = SimulationConfig(
                input_dir=input_dir, plantel=REQUIRED_FILES["plantel"],
                tanques=REQUIRED_FILES["tanques"], curvas=REQUIRED_FILES["curvas"],
                racao=REQUIRED_FILES["racao"], output=output_name,
                data_relatorio=data_relatorio, mostrar_erros=mostrar_erros,
            )
            try:
                input_dir.mkdir(parents=True, exist_ok=True)
                (input_dir / PARAMETROS_FILE).write_bytes(
                    parametros_gerenciais_to_csv(df_metas, df_terceiros)
                )
                with st.spinner("Motor de Cálculo em Execução..."):
                    out_path, stdout = run_simulation(config)
                st.session_state["last_artifact"] = ReportArtifact(out_path.name, out_path.read_bytes(), stdout, str(out_path))
            except Exception as e:
                st.error(f"Falha Crítica na Execução: {e}")

    # Renderização Condicional do Relatório Gerado
    artifact = st.session_state.get("last_artifact")
    if artifact:
        st.success("✅ Simulação e Processamento de Dados concluídos com sucesso!")
        st.download_button(
            label="📥 Baixar CSV completo da simulação",
            data=artifact.output_bytes,
            file_name=artifact.file_name,
            mime="text/csv",
            use_container_width=True,
            key="download_full_simulation_csv",
        )
        st.divider()
        render_excel_style_view(artifact.output_bytes)

if __name__ == "__main__":
    main()
