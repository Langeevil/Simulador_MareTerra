from __future__ import annotations

import argparse
import base64
import csv
import html
import importlib
import io
import os
import sys
import tempfile
import re
from collections import defaultdict
from contextlib import redirect_stdout
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import numpy as np
import altair as alt
import pandas as pd
import streamlit as st

# Configuração de Paths do Sistema
ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
APP_DIR = ROOT_DIR / "app"
MATH_DIR = ROOT_DIR / "math"
for import_dir in (SRC_DIR, APP_DIR, MATH_DIR):
    if str(import_dir) not in sys.path:
        sys.path.insert(0, str(import_dir))

from calculos_saldo import calcular_saldo_acumulado_mes
import calculos_movimentacao
from theme_config import PatternName, is_display_numeric_value, normalize_label, style_dark_regional_report
from theme_consolidado import style_consolidado_dataframe

calculos_movimentacao = importlib.reload(calculos_movimentacao)
calcular_saldo_acumulado_consolidado = calculos_movimentacao.calcular_saldo_acumulado_consolidado
calcular_po_atualizado_no_mes_saldo_consolidado = (
    calculos_movimentacao.calcular_po_atualizado_no_mes_saldo_consolidado
)
calcular_total_kg_mes_disponivel_abate_consolidado = (
    calculos_movimentacao.calcular_total_kg_mes_disponivel_abate_consolidado
)
referenciar_saldo_atualizado_dia = calculos_movimentacao.referenciar_saldo_atualizado_dia
referenciar_po_regional = calculos_movimentacao.referenciar_po_regional
calcular_total_kg_dia_disponivel_abate = (
    calculos_movimentacao.calcular_total_kg_dia_disponivel_abate
)
referenciar_saldo_acumulado_regional = calculos_movimentacao.referenciar_saldo_acumulado_regional
calcular_saldo_po_atual_disponivel_dia = (
    calculos_movimentacao.calcular_saldo_po_atual_disponivel_dia
)

# Tentativa de importação do motor da simulação
try:
    from simulador_aquicola import (
        carregar_csv,
        executar,
        preparar_curvas,
        preparar_parametros_gerenciais,
    )
except ImportError:
    st.error("Erro Crítico: Módulo 'simulador_aquicola' não encontrado. Verifique a estrutura do projeto.")
    st.stop()

# Constantes da Aplicação
APP_TITLE = "Simulador de Planejamento Aquícola - Mar & Terra"
DEFAULT_OUTPUT = "simulacao_completa_br.csv"
BRAND_GREEN = "#17413B"
BRAND_GOLD = "#BC933F"
CHART_COLORS = [
    "#0F6B5F",  # verde petroleo da marca, mais legivel em fundo claro/escuro
    "#D6A33A",  # dourado da marca com mais luminosidade para linhas finas
    "#2563EB",  # azul complementar para diferenciar a terceira serie
]
LOGO_WHITE = ROOT_DIR / "app" / "assets" / "mar-terra-logo-branca.png"
LOGO_BLACK = ROOT_DIR / "app" / "assets" / "mar-terra-logo-preta.png"
REQUIRED_FILES = {
    "plantel": "plantel.csv",
    "tanques": "tanques.csv",
    "curvas": "curvas.csv",
    "racao": "racao.csv",
    "parametros_gerenciais": "parametros_gerenciais.csv",
}
PARAMETROS_FILE = "parametros_gerenciais.csv"


def runtime_root() -> Path:
    runtime_dir = os.environ.get("SIMULADOR_RUNTIME_DIR")
    if runtime_dir:
        return Path(runtime_dir).resolve()
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return ROOT_DIR


RUNTIME_DIR = runtime_root()


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
    parametros_gerenciais: str
    output: str
    data_relatorio: date
    mostrar_erros: bool

@dataclass(frozen=True)
class ReportArtifact:
    file_name: str
    output_bytes: bytes
    captured_output: str = ""
    output_path: str | None = None


@dataclass(frozen=True)
class RegionalReportSection:
    base_title: str
    pattern: PatternName
    start_marker: str


REGIONAL_REPORT_SECTIONS: tuple[RegionalReportSection, ...] = (
    RegionalReportSection("QUADRO DE PEIXE GORDO - PRÓPRIO", "A", "quadro de peixe gordo - proprio"),
    RegionalReportSection("QUADRO DE PEIXE GORDO - INTEGRAÇÃO", "B", "quadro de peixe gordo - integracao"),
    RegionalReportSection("QUADRO DE PEIXE GORDO - PARCERIA", "C", "quadro de peixe gordo - parceria"),
    RegionalReportSection("QUADRO DE PEIXE GORDO TOTAL", "A", "quadro de peixe gordo total"),
    RegionalReportSection("QUADRO DE DISPONIBILIDADE PARA O ABATE POR DIA", "B", "quadro de disponibilidade para o abate por dia"),
    RegionalReportSection("QUADRO DO SALDO DA DISPONIBILIDADE PARA O ABATE POR DIA e POR MÊS", "B", "quadro do saldo da disponibilidade"),
)

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
        initial_sidebar_state="collapsed",
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
        
        /* Refinamento Visual das Abas (Tabs) para Padrão Executivo */
        .stTabs [data-baseweb="tab-list"] { gap: 10px; border-bottom: 1px solid #E7D8B5; }
        .stTabs [data-baseweb="tab"] { 
            height: 50px; padding: 0 16px; background-color: transparent; 
            border-radius: 6px 6px 0 0; color: var(--text-color) !important; font-weight: 600; 
            transition: all 0.2s ease-in-out;
        }
        .stTabs [data-baseweb="tab"] p,
        .stTabs [data-baseweb="tab"] span {
            color: var(--text-color) !important;
        }
        .stTabs [aria-selected="true"] { 
            background-color: rgba(188, 147, 63, 0.15) !important; 
            color: var(--text-color) !important; border-bottom: 3px solid #17413B !important; 
        }
        .stTabs [aria-selected="true"] p,
        .stTabs [aria-selected="true"] span {
            color: var(--text-color) !important;
        }
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
            'fase nutricional': 'fase_nutricional',
            'status': 'status',
            'produtor': 'produtor',
            'tanque': 'tanque',
            'classe': 'classe',
            'data': 'data',
            'consumo de racao diario (kg)': 'consumo_racao_diario_kg',
            'consumo de ração diario (kg)': 'consumo_racao_diario_kg',
            'consumo de racao na fase (kg)': 'consumo_racao_na_fase_kg',
            'consumo de ração na fase (kg)': 'consumo_racao_na_fase_kg',
            'consumo de racao acumulado (kg)': 'consumo_racao_acumulado_kg',
            'consumo de ração acumulado (kg)': 'consumo_racao_acumulado_kg',
            'ganho de biomassa acumulado (kg)': 'ganho_biomassa_acumulado_kg',
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
            'ganho_biomassa_acumulado_kg',
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
    numero = pd.to_numeric(valores[0], errors="coerce")
    return float(numero) if pd.notna(numero) else 0.0


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


METAS_COLUMNS = ["Mês", "Dias Abate APT", "PO Diário APT (kg)", "Dias Abate ITA", "PO Diário ITA (kg)"]
TERCEIROS_COLUMNS = ["Região Destino", "Classe", "Produtor", "Mês", "Volume (kg)"]


def empty_management_frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    return pd.DataFrame(columns=METAS_COLUMNS), pd.DataFrame(columns=TERCEIROS_COLUMNS)


def integer_or_blank(valor: object) -> int | None:
    texto = str(valor).strip()
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    elif "." in texto:
        partes = texto.split(".")
        if len(partes) > 2 or (len(partes) == 2 and len(partes[1]) == 3 and len(partes[0]) <= 3):
            texto = texto.replace(".", "")
    numero = pd.to_numeric(texto, errors="coerce")
    return int(round(float(numero))) if pd.notna(numero) else None


def csv_numero_or_blank(valor: object) -> object:
    if pd.isna(valor):
        return ""
    numero = integer_or_blank(valor)
    if numero is None:
        return ""
    return str(numero)


def parse_parametros_gerenciais(csv_bytes: bytes, data_inicio: date, num_meses: int = 12) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not csv_bytes:
        return empty_management_frames()

    raw = pd.read_csv(io.BytesIO(csv_bytes), sep=';', encoding='utf-8-sig', dtype=str).fillna("")
    parametros = preparar_parametros_gerenciais(raw)

    metas = parametros["metas"].copy()
    abate = parametros["abate"].copy()
    transferencias = parametros["transferencias"].copy()

    meses = sorted({
        str(mes).strip()
        for df in (metas, abate, transferencias)
        for mes in df.get("mes", pd.Series(dtype=str)).tolist()
        if str(mes).strip()
    })
    df_metas = pd.DataFrame({"Mês": meses}, columns=METAS_COLUMNS)
    for coluna in METAS_COLUMNS[1:]:
        df_metas[coluna] = None

    for _, row in metas.iterrows():
        mes = str(row.get("mes", "")).strip()
        regiao = str(row.get("regiao", "")).strip().upper()
        if mes not in set(df_metas["Mês"]) or regiao not in {"APT", "ITA"}:
            continue
        idx = df_metas["Mês"] == mes
        df_metas.loc[idx, f"PO Diário {regiao} (kg)"] = integer_or_blank(row.get("po_diario_kg", ""))

    for _, row in abate.iterrows():
        mes = str(row.get("mes", "")).strip()
        regiao = str(row.get("regiao", "")).strip().upper()
        if mes not in set(df_metas["Mês"]) or regiao not in {"APT", "ITA"}:
            continue
        idx = df_metas["Mês"] == mes
        df_metas.loc[idx, f"Dias Abate {regiao}"] = integer_or_blank(row.get("dias_abate", ""))

    rows = []
    for _, row in transferencias.iterrows():
        mes = str(row.get("mes", "")).strip()
        regiao = str(row.get("regiao", "")).strip().upper()
        if mes and regiao in {"APT", "ITA"}:
            rows.append({
                "Região Destino": regiao,
                "Classe": str(row.get("classe", "")).strip(),
                "Produtor": str(row.get("produtor", "")).strip(),
                "Mês": mes,
                "Volume (kg)": integer_or_blank(row.get("volume_kg", "")),
            })
    df_terceiros = pd.DataFrame(rows, columns=TERCEIROS_COLUMNS)
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
                "dias_abate": csv_numero_or_blank(row.get(f"Dias Abate {regiao}", "")),
                "po_diario_kg": csv_numero_or_blank(row.get(f"PO Diário {regiao} (kg)", "")),
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
                "volume_kg": csv_numero_or_blank(row.get("Volume (kg)", "")),
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
        # total_label = (
        #     "Previsão de Disponibilidade Próprio" if cl == "Próprio"
        #     else "Previsão de Disponibilidade Integração" if cl == "Integração"
        #     else "Previsão de Disponibilidade Parceria" if cl == "Parceria"
        #     else f"Total {cl}"
        # )
        # t_dict = {"Conteúdo / Bloco": total_label}
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
    # Regra anterior: as abas regionais nao tinham linha PO separada.
    output_rows.append({"Conteúdo / Bloco": "PO", **po_diario})
    output_rows.append({"Conteúdo / Bloco": "Saldo Atualizado / dia", **saldo_dia})

    df_saldo_mes = pd.DataFrame({"Mês": months})
    df_saldo_mes["Região"] = region
    df_saldo_mes["Saldo Atualizado / dia"] = df_saldo_mes["Mês"].map(saldo_dia)
    df_saldo_mes["Dias de Abate"] = df_saldo_mes["Mês"].map(dias_abate)
    df_saldo_mes["Saldo Acm Atualizado / mês"] = calcular_saldo_acumulado_mes(
        df_saldo_mes,
        col_saldo_dia="Saldo Atualizado / dia",
        col_dias_abate="Dias de Abate",
        col_agrupamento="Região",
    )
    saldo_acm = df_saldo_mes.set_index("Mês")["Saldo Acm Atualizado / mês"].to_dict()
        
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

    def title_cells(parts: list[str]) -> dict[str, str]:
        if not months:
            return {}
        if len(parts) > len(months):
            parts = [*parts[: len(months) - 1], " ".join(parts[len(months) - 1:])]
        parts = [*parts, *([""] * (len(months) - len(parts)))]
        return dict(zip(months, parts))

    def title_row(label: str, availability: str, period: str, region: str) -> dict[str, object]:
        availability_parts = (
            ["DISPONIBILIDADE", "DE BIOMASSA"]
            if normalize_label(availability) == "disponibilidade de biomassa"
            else [availability.upper()]
        )
        return {
            "Conteúdo / Bloco": label,
            **title_cells(["QUADRO DE", *availability_parts, f"PARA O ABATE {period.upper()}", region.upper()]),
        }

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
        "po_atualizado": row_values(df_apt, "PO Atualizado"),
        "po": row_values(df_apt, "PO"),
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
        "po_atualizado": row_values(df_ita, "PO Atualizado"),
        "po": row_values(df_ita, "PO"),
        "saldo_dia": row_values(df_ita, "Saldo Atualizado / dia"),
        "saldo_acm": row_values(df_ita, "Saldo Acm Atualizado / mês"),
        "total_mes": row_values(df_ita, "Previsão Disponibilidade Total"),
        "peso_medio": weighted_avg_weight("ITA"),
    }
    # Regra anterior para APT:
    # apt["total_dia"] = row_values(df_apt, "Total Kg/Dia Disponível Abate")
    apt["total_dia"] = calcular_total_kg_dia_disponivel_abate(
        apt["kg_proprio"],
        apt["kg_integracao"],
        apt["kg_parceria"],
        months,
    )

    def regional_block(
        region_name: str,
        data: dict[str, dict[str, float]],
        *,
        availability: str,
        region_code: str,
    ) -> None:
        output_rows.append(title_row(region_name, availability, "Dia", region_code))
        output_rows.append({"Conteúdo / Bloco": "Dias de Abate", **data["dias"]})
        output_rows.append({"Conteúdo / Bloco": "Kg/Dia Próprio", **data["kg_proprio"]})
        output_rows.append({"Conteúdo / Bloco": "Kg/Dia Integração", **data["kg_integracao"]})
        output_rows.append({"Conteúdo / Bloco": "Kg/Dia Parceria", **data["kg_parceria"]})
        output_rows.append({"Conteúdo / Bloco": "Total Kg/Dia Dispon Abate", **data["total_dia"]})
        output_rows.append({"Conteúdo / Bloco": "PO Atualizado", **data["po_atualizado"]})
        if region_code == "ITA":
            # Regra anterior para ITA:
            # po_regional = data["po_atualizado"]
            po_regional = referenciar_po_regional(data["po"], months)
        else:
            po_regional = data["po"]
        output_rows.append({"Conteúdo / Bloco": "PO", **po_regional})
        if region_code == "APT":
            # Regras anteriores para APT:
            # saldo_po_atual_disponivel = multiply_series(data["saldo_dia"], data["dias"])
            # saldo_po_atual_disponivel = referenciar_saldo_acumulado_regional(data["saldo_acm"], months)
            saldo_po_atual_disponivel = calcular_saldo_po_atual_disponivel_dia(
                data["total_dia"],
                data["po_atualizado"],
                months,
            )
        elif region_code == "ITA":
            # Regra anterior para ITA:
            # saldo_po_atual_disponivel = multiply_series(data["saldo_dia"], data["dias"])
            saldo_po_atual_disponivel = referenciar_saldo_atualizado_dia(data["saldo_dia"], months)
        else:
            saldo_po_atual_disponivel = multiply_series(data["saldo_dia"], data["dias"])
        output_rows.append({
            "Conteúdo / Bloco": "Saldo PO Atual. x Disponível",
            **saldo_po_atual_disponivel,
        })
        output_rows.append({"Conteúdo / Bloco": "Peso Médio", **data["peso_medio"]})
        output_rows.append(empty_row())

    regional_block("APT", apt, availability="Disponibilidade", region_code="APT")
    regional_block("ITA", ita, availability="Disponibilidade de Biomassa", region_code="ITA")

    geral_total_dia = sum_series(apt["total_dia"], ita["total_dia"])
    geral_po_atualizado = sum_series(apt["po_atualizado"], ita["po_atualizado"])
    geral_po = sum_series(apt["po"], ita["po"])
    geral_saldo_atualizado_dia = diff_series(geral_total_dia, geral_po_atualizado)
    geral_saldo_dia = diff_series(geral_total_dia, geral_po)
    # Regra anterior para "Total Kg/Mês Disponível Abate":
    # geral_total_mes = sum_series(apt["total_mes"], ita["total_mes"])
    geral_total_mes = calcular_total_kg_mes_disponivel_abate_consolidado(
        apt["total_dia"],
        apt["dias"],
        ita["total_dia"],
        ita["dias"],
        months,
    )
    # Regra anterior para "PO Atualizado (No mês) Saldo":
    # geral_abate_po_mes = sum_series(
    #     multiply_series(apt["po"], apt["dias"]),
    #     multiply_series(ita["po"], ita["dias"]),
    # )
    # geral_saldo_mes = diff_series(geral_total_mes, geral_abate_po_mes)
    geral_saldo_mes = calcular_po_atualizado_no_mes_saldo_consolidado(
        geral_saldo_atualizado_dia,
        ita["dias"],
        months,
    )
    
    # Regra anterior do consolidado: recalculava o acumulado geral usando os dias de abate da APT.
    # geral_dias_abate = apt["dias"]
    # df_geral_saldo_mes = pd.DataFrame({"Mês": months})
    # df_geral_saldo_mes["Grupo"] = "GERAL"
    # df_geral_saldo_mes["Saldo PO Atualizado"] = df_geral_saldo_mes["Mês"].map(geral_saldo_dia)
    # df_geral_saldo_mes["Dias de Abate"] = df_geral_saldo_mes["Mês"].map(geral_dias_abate)
    # df_geral_saldo_mes["Saldo Acm Atualizado / mês"] = calcular_saldo_acumulado_mes(
    #     df_geral_saldo_mes,
    #     col_saldo_dia="Saldo PO Atualizado",
    #     col_dias_abate="Dias de Abate",
    #     col_agrupamento="Grupo",
    # )
    # geral_saldo_acm = df_geral_saldo_mes.set_index("Mês")["Saldo Acm Atualizado / mês"].to_dict()
    geral_saldo_acm = calcular_saldo_acumulado_consolidado(
        apt["saldo_acm"],
        ita["saldo_acm"],
        months,
    )

    output_rows.append(title_row("QUADRO DE", "Disponibilidade", "Dia", "GERAL"))
    output_rows.append({"Conteúdo / Bloco": "Total Kg/Dia Disponível Abate", **geral_total_dia})
    output_rows.append({"Conteúdo / Bloco": "PO Atualizado", **geral_po_atualizado})
    output_rows.append({"Conteúdo / Bloco": "PO", **geral_po})
    output_rows.append({"Conteúdo / Bloco": "Saldo PO Atualizado", **geral_saldo_atualizado_dia})
    output_rows.append({"Conteúdo / Bloco": "Saldo PO", **geral_saldo_dia})
    output_rows.append(empty_row())

    output_rows.append(title_row("QUADRO DE", "Disponibilidade", "Mês", "GERAL"))
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


def auto_width_column_config(
    df: pd.DataFrame,
    *,
    min_width: int = 92,
    max_width: int = 420,
    label_min_width: int = 260,
    label_max_width: int = 520,
) -> dict[str, object]:
    """Define larguras por coluna com base no maior texto exibido."""

    def visible_text_length(value: object) -> int:
        if pd.isna(value):
            return 0
        text = str(value)
        return max((len(part) for part in text.splitlines()), default=0)

    column_config: dict[str, object] = {}
    for column in df.columns:
        header = str(column)
        max_chars = max([visible_text_length(header), *df[column].map(visible_text_length).tolist()])

        is_label_column = normalize_label(header) == "conteudo / bloco"
        has_numeric_values = any(is_display_numeric_value(value) for value in df[column].tolist())

        if is_label_column:
            width = max(label_min_width, min(label_max_width, (max_chars * 8) + 36))
        else:
            width = max(min_width, min(max_width, (max_chars * 8) + 36))

        column_config[header] = st.column_config.Column(
            header,
            width=int(width),
            alignment="left" if is_label_column else ("center" if has_numeric_values else "left"),
        )

    return column_config


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


def render_line_chart(
    chart_df: pd.DataFrame,
    title: str,
    y_title: str,
    *,
    selected_month: str | None = None,
) -> None:
    """Renderiza gráficos com eixos explícitos para evitar leituras ambíguas."""
    if chart_df.empty:
        return

    st.markdown(f"#### {title}")

    chart_data = (
        chart_df.reset_index(names="Mês")
        .melt(id_vars="Mês", var_name="Indicador", value_name="Valor")
    )
    line_chart = (
        alt.Chart(chart_data)
        .mark_line(point=alt.OverlayMarkDef(filled=True, size=72), strokeWidth=3.2)
        .encode(
            x=alt.X("Mês:O", title="Mês / Tempo", sort=None, axis=alt.Axis(labelAngle=0)),
            y=alt.Y("Valor:Q", title=y_title, scale=alt.Scale(zero=False)),
            color=alt.Color(
                "Indicador:N",
                title="Série",
                scale=alt.Scale(range=CHART_COLORS),
                legend=alt.Legend(
                    orient="bottom",
                    direction="horizontal",
                    titleFontSize=12,
                    labelFontSize=12,
                    symbolSize=140,
                ),
            ),
            tooltip=[
                alt.Tooltip("Mês:O", title="Mês"),
                alt.Tooltip("Indicador:N", title="Série"),
                alt.Tooltip("Valor:Q", title=y_title, format=",.2f"),
            ],
        )
        .properties(height=320)
    )

    chart = line_chart
    if selected_month:
        selected_data = chart_data[chart_data["Mês"].astype(str) == selected_month]
        selected_rule = (
            alt.Chart(pd.DataFrame({"Mês": [selected_month]}))
            .mark_rule(color=BRAND_GOLD, strokeDash=[6, 4], strokeWidth=2, opacity=0.95)
            .encode(x=alt.X("Mês:O", sort=None))
        )
        selected_points = (
            alt.Chart(selected_data)
            .mark_point(filled=False, size=190, strokeWidth=3)
            .encode(
                x=alt.X("Mês:O", title="Mês / Tempo", sort=None),
                y=alt.Y("Valor:Q", title=y_title),
                color=alt.Color("Indicador:N", scale=alt.Scale(range=CHART_COLORS), legend=None),
                tooltip=[
                    alt.Tooltip("Mês:O", title="Mês"),
                    alt.Tooltip("Indicador:N", title="Série"),
                    alt.Tooltip("Valor:Q", title=y_title, format=",.2f"),
                ],
            )
        )
        chart = alt.layer(line_chart, selected_rule, selected_points).properties(height=320)

    chart = chart.configure_axis(labelFontSize=12, titleFontSize=13).configure_legend(
        labelFontSize=12,
        titleFontSize=12,
    )
    st.altair_chart(chart, use_container_width=True)


def styled_report_dataframe(df: pd.DataFrame) -> pd.io.formats.style.Styler:
    """Aplica alternância de linhas e destaque visual com contraste WCAG."""

    def row_style(row: pd.Series) -> list[str]:
        label = str(row.get("Conteúdo / Bloco", "")).lower()
        size = len(row)

        if not label.strip():
            return ["background-color: transparent;"] * size
            
        if "previsão disponibilidade total" in label or "previsao disponibilidade total" in label:
            return [
                "background-color: #17413B; color: #FFFFFF; font-weight: 900; border-top: 2px solid #BC933F;"
            ] * size
        if "abate po atualizado total" in label:
            return [
                "background-color: #BC933F; color: #111827; font-weight: 900; border-bottom: 2px solid #17413B;"
            ] * size
        if "próprio" in label or "proprio" in label:
            return [
                "background-color: #17413B; color: #FFFFFF; font-weight: 800;"
            ] * size
        if "integração" in label or "integracao" in label:
            return [
                "background-color: #BC933F; color: #111827; font-weight: 800;"
            ] * size
        if "parceria" in label:
            return [
                "background-color: #748D89; color: #111827; font-weight: 800;"
            ] * size
        if label == "dias de abate":
            return [
                "background-color: #BC933F; color: #111827; font-weight: 900;"
            ] * size
        if "quadro" in label:
            return [
                "background-color: rgba(23, 65, 59, 0.85); color: #FFFFFF; font-weight: 800;"
            ] * size
        if label in {"apt", "itaporã", "itapora"}:
            return [
                "background-color: rgba(188, 147, 63, 0.85); color: #111827; font-weight: 800;"
            ] * size
        if "total" in label:
            return [
                "background-color: #DCE2E2; color: #111827; font-weight: 800;"
            ] * size
        if "saldo" in label:
            return [
                "background-color: #F2E9D9; color: #111827; font-weight: 800;"
            ] * size
        if label in {"po", "po atualizado"} or "po atualizado" in label:
            return [
                "background-color: #F5EFE2; color: #111827; font-weight: 800;"
            ] * size
        if any(marker in label for marker in ["biometria", "liberado", "disponivel", "disponível"]):
            return [
                "background-color: #DCE2E2; color: #111827; font-weight: 800;"
            ] * size
        if isinstance(row.name, int) and row.name % 2 == 0:
            return ["background-color: #F8F4EC; color: #111827;"] * size
        return ["background-color: #FFFFFF; color: #111827;"] * size

    return (
        df.style.apply(row_style, axis=1)
        .set_properties(
            subset=["Conteúdo / Bloco"],
            **{
                "min-width": "350px",
                "max-width": "450px",
                "white-space": "normal",
                "word-wrap": "break-word",
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
                        ("text-align", "center"),
                        ("border-bottom", "3px solid #BC933F"),
                    ],
                }
            ]
        )
        .hide(axis="index")
    )


def render_report_dataframe(
    df: pd.DataFrame,
    *,
    height: int,
    use_dark_theme: bool = False,
) -> None:
    display_df = format_df_for_display(df)
    column_config = auto_width_column_config(display_df)

    if not use_dark_theme:
        st.dataframe(
            styled_report_dataframe(display_df),
            use_container_width=True,
            height=height,
            column_config=column_config,
        )
        return

    try:
        styler = style_dark_regional_report(display_df)
    except ValueError as exc:
        st.warning(f"Nao foi possivel aplicar o tema escuro regional: {exc}")
        styler = styled_report_dataframe(display_df)

    st.dataframe(styler, use_container_width=True, height=height, column_config=column_config)


def _col_letter(col_idx: int) -> str:
    letter = ""
    while col_idx >= 0:
        letter = chr(col_idx % 26 + 65) + letter
        col_idx = col_idx // 26 - 1
    return letter


def audit_csv_formulas(csv_bytes: bytes) -> pd.DataFrame:
    """Inspeciona um arquivo CSV e aponta erros prováveis (#REF!, referências circulares, etc)."""
    issues: list[dict[str, str]] = []
    try:
        df = pd.read_csv(io.BytesIO(csv_bytes), sep=';', encoding='utf-8-sig', dtype=str)
        if df.shape[1] == 1:
            df = pd.read_csv(io.BytesIO(csv_bytes), sep=',', encoding='utf-8-sig', dtype=str)
    except Exception:
        df = pd.read_csv(io.BytesIO(csv_bytes), sep=',', encoding='utf-8', dtype=str)

    for row_idx, row in df.iterrows():
        for col_idx, (col_name, value) in enumerate(row.items()):
            if pd.isna(value):
                continue
            val_str = str(value).strip()
            if not val_str:
                continue
            
            cell_ref = f"{_col_letter(col_idx)}{row_idx + 2}"
            problem = ""
            
            if "#REF!" in val_str.upper():
                problem = "Referência quebrada (#REF!)"
            elif val_str.startswith("="):
                if re.search(rf"(?<![A-Z0-9]){re.escape(cell_ref)}(?![A-Z0-9])", val_str, re.I):
                    problem = "Possível referência circular direta"
                elif re.search(r":\s*$|,\s*$|;\s*$", val_str):
                    problem = "Fórmula possivelmente incompleta"
            elif any(err in val_str.upper() for err in ["#VALUE!", "#DIV/0!", "#NAME?", "#N/A", "#NUM!"]):
                problem = "Erro de cálculo exportado"

            if problem:
                issues.append(
                    {
                        "Célula": cell_ref,
                        "Coluna Origem": str(col_name),
                        "Problema": problem,
                        "Conteúdo": val_str,
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
    key_prefix: str = "management",
    save_path: Path | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    st.divider()
    title_col, action_col = st.columns([0.74, 0.26])
    with title_col:
        st.subheader("📊 Parâmetros Gerenciais e Metas")
        st.caption("Insira e ajuste as metas comerciais, dias operacionais e volumes extras antes de simular.")
    with action_col:
        save_action_slot = st.empty()
    saved_toast_key = f"{key_prefix}_parametros_saved_toast"
    if st.session_state.pop(saved_toast_key, False):
        st.toast("parametros_gerenciais.csv salvo com sucesso.", icon="✅")
    
    df_metas_base, df_terceiros_base = parse_parametros_gerenciais(parametros_bytes or b"", data_inicio, num_meses)
    meses = df_metas_base["Mês"].tolist()
        
    col1, col2 = st.columns([1.1, 0.9])
    
    with col1:
        st.markdown("#### 1. Metas (PO) e Dias de Abate por Região")
        df_metas_editado = st.data_editor(
            df_metas_base,
            use_container_width=True,
            hide_index=True,
            key=f"{key_prefix}_metas_editor_{data_inicio.isoformat()}_{hash(parametros_bytes)}",
            column_config={
                "Mês": st.column_config.TextColumn("Mês", disabled=True),
                "Dias Abate APT": st.column_config.NumberColumn("Dias Abate APT", min_value=1, step=1, format="%d"),
                "PO Diário APT (kg)": st.column_config.NumberColumn("PO Diário APT (kg)", min_value=0, step=1000, format="%d"),
                "Dias Abate ITA": st.column_config.NumberColumn("Dias Abate ITA", min_value=1, step=1, format="%d"),
                "PO Diário ITA (kg)": st.column_config.NumberColumn("PO Diário ITA (kg)", min_value=0, step=1000, format="%d"),
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
                "Volume (kg)": st.column_config.NumberColumn("Volume (kg)", required=True, step=1000, format="%d"),
                "Produtor": st.column_config.TextColumn("Produtor", required=True)
            },
            key=f"{key_prefix}_terceiros_editor_{data_inicio.isoformat()}_{hash(parametros_bytes)}"
        )

    meses_visiveis = st.multiselect(
        "Meses exibidos no relatório da tela",
        options=meses,
        default=meses,
        key=f"{key_prefix}_meses_visiveis",
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
        key=f"{key_prefix}_download_parametros_gerenciais",
    )
    if save_path is not None:
        with save_action_slot.container():
            salvar_parametros = st.button(
                "SALVAR ALTERAÇÕES",
                use_container_width=True,
                key=f"{key_prefix}_save_parametros_gerenciais",
            )
            st.markdown(
                """
                <div style="
                    width: 100%;
                    font-size: 0.875rem;
                    color: rgba(49, 51, 63, 0.6);
                    line-height: 1.35;
                ">
                    Sobrescreve os dados no arquivo de parâmetros gerenciais com os dados alterados na tabela.
                </div>
                """,
                unsafe_allow_html=True,
            )
        if salvar_parametros:
            save_path.parent.mkdir(parents=True, exist_ok=True)
            save_path.write_bytes(parametros_csv)
            st.session_state["df_metas"] = df_metas_editado.copy()
            st.session_state["df_terceiros"] = df_terceiros_editado.copy()
            st.session_state["meses_visiveis"] = list(meses_visiveis)
            st.session_state[f"{key_prefix}_parametros_file_mtime_ns"] = save_path.stat().st_mtime_ns
            st.session_state[f"{key_prefix}_parametros_override_bytes"] = parametros_csv
            st.session_state[saved_toast_key] = True
            st.rerun()

    return df_metas_editado, df_terceiros_editado, meses_visiveis


def render_validated_management_inputs(
    data_inicio: date,
    parametros_bytes: bytes | None,
    key_prefix: str,
    save_path: Path | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, list[str]] | None:
    if parametros_bytes is None:
        return None

    try:
        return render_management_inputs(
            data_inicio,
            num_meses=12,
            parametros_bytes=parametros_bytes,
            key_prefix=key_prefix,
            save_path=save_path,
        )
    except ValueError as exc:
        st.error(f"parametros_gerenciais.csv invalido: {exc}")
    except Exception as exc:
        st.error(f"Nao foi possivel ler parametros_gerenciais.csv: {exc}")
    return None


@st.fragment(run_every="2s")
def watch_parametros_gerenciais_file(path: Path, key_prefix: str) -> None:
    if not path.exists():
        return

    state_key = f"{key_prefix}_parametros_file_mtime_ns"
    toast_key = f"{key_prefix}_parametros_external_update_toast"
    current_mtime = path.stat().st_mtime_ns
    previous_mtime = st.session_state.get(state_key)

    if previous_mtime is None:
        st.session_state[state_key] = current_mtime
        return

    if current_mtime != previous_mtime:
        st.session_state[state_key] = current_mtime
        st.session_state[toast_key] = True
        st.rerun()


def render_spreadsheet_audit() -> None:
    with st.expander("Auditoria opcional da planilha base"):
        st.caption("Verifica valores e fórmulas exportadas com #REF!, possível referência circular direta e fórmulas aparentemente incompletas.")
        workbook = st.file_uploader(
            "Planilha base de projeção (.csv)",
            type=["csv"],
            key="audit_workbook_upload",
        )
        if workbook is None:
            return
        try:
            issues = audit_csv_formulas(workbook.getvalue())
        except Exception as exc:
            st.error(f"Não foi possível auditar a planilha: {exc}")
            return
        if issues.empty:
            st.success("Nenhum problema evidente encontrado nas fórmulas auditadas.")
        else:
            st.warning(f"Foram encontrados {len(issues)} ponto(s) para revisão.")
            st.dataframe(
                issues,
                use_container_width=True,
                hide_index=True,
                column_config=auto_width_column_config(issues),
            )


def curvas_cluster_dataframe_from_path(path: Path) -> pd.DataFrame:
    curvas = preparar_curvas(carregar_csv(path))
    rows = []
    for curva in curvas:
        cluster = str(curva.get("cluster", "") or "Curva padrão").strip() or "Curva padrão"
        rows.append(
            {
                "Dia": int(curva["dia"]),
                "Tipo de Curva": "Verão" if curva["estacao"] == "V" else "Inverno",
                "Cluster": cluster,
                "Peso Médio (g)": float(curva["peso_ref_g"]),
                "GDP (g/dia)": float(curva["gdp_g"]),
                "Mortalidade (%)": float(curva["mortalidade_pct"]),
            }
        )
    curvas_df = pd.DataFrame(rows)
    if curvas_df.empty:
        return curvas_df

    ordem_tipo_curva = {"Inverno": 0, "Verão": 1}
    curvas_df["_ordem_tipo_curva"] = curvas_df["Tipo de Curva"].map(ordem_tipo_curva).fillna(2)
    return (
        curvas_df.sort_values(["Dia", "_ordem_tipo_curva", "Cluster"])
        .drop(columns="_ordem_tipo_curva")
        .reset_index(drop=True)
    )


def curvas_cluster_dataframe_from_bytes(csv_bytes: bytes) -> pd.DataFrame:
    with tempfile.TemporaryDirectory() as temp_dir:
        path = Path(temp_dir) / "curvas.csv"
        path.write_bytes(csv_bytes)
        return curvas_cluster_dataframe_from_path(path)


def render_curve_programs_preview(curvas_df: pd.DataFrame) -> None:
    if curvas_df.empty:
        return

    with st.expander("Comparativo de programas / curvas por cluster", expanded=False):
        display_df = curvas_df.copy()
        display_df["_ordem_tipo_curva"] = display_df["Tipo de Curva"].map({"Inverno": 0, "Verão": 1}).fillna(2)
        display_df = (
            display_df.sort_values(["Dia", "_ordem_tipo_curva", "Cluster"])
            .drop(columns="_ordem_tipo_curva")
            .reset_index(drop=True)
        )
        height = min(620, max(260, 38 * (len(display_df) + 1)))
        st.dataframe(
            display_df,
            use_container_width=True,
            hide_index=True,
            height=height,
            column_config=auto_width_column_config(display_df),
        )

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
        ["🏭 APT (Aparecida do Taboado)", "🏭 ITA (Itaporã)", "📊 Consolidado APT + ITA"]
    )
    with tab_apt:
        chart_apt = dataframe_for_chart(
            df_apt_raw,
            ["Previsão Disponibilidade Total", "Abate PO Atualizado Total Mês"],
        )
        if not chart_apt.empty:
            render_line_chart(chart_apt, "APT - Biomassa disponível x PO mensal", "Biomassa / abate projetado (kg)")
        render_report_dataframe(df_apt_raw, height=550, use_dark_theme=True)
    with tab_ita:
        chart_ita = dataframe_for_chart(
            df_ita_raw,
            ["Previsão Disponibilidade Total", "Abate PO Atualizado Total Mês"],
        )
        if not chart_ita.empty:
            render_line_chart(chart_ita, "ITA - Biomassa disponível x PO mensal", "Biomassa / abate projetado (kg)")
        render_report_dataframe(df_ita_raw, height=550, use_dark_theme=True)
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
            meses_consolidado = [str(mes) for mes in chart_consolidado.index]
            mes_atual = date.today().strftime("%Y-%m")
            mes_padrao_idx = meses_consolidado.index(mes_atual) if mes_atual in meses_consolidado else len(meses_consolidado) - 1

            # Código anterior: exibia sempre o último valor relevante de cada série.
            # metric_cols = st.columns(3)
            # for col, label in zip(metric_cols, chart_consolidado.columns[:3]):
            #     col.metric(label, format_br_number(ultimo_valor_relevante(chart_consolidado[label]), 0))

            card_col_1, card_col_2, card_col_3, selector_col = st.columns([1, 1, 1, 0.58])
            with selector_col:
                mes_selecionado = st.selectbox(
                    "Mês",
                    options=meses_consolidado,
                    index=mes_padrao_idx,
                    key="consolidado_mes_cards",
                )

            for col, label in zip([card_col_1, card_col_2, card_col_3], chart_consolidado.columns[:3]):
                valor_mes = chart_consolidado.loc[mes_selecionado, label]
                col.metric(label, format_br_number(valor_mes, 0))
            render_line_chart(
                chart_consolidado,
                "Consolidado APT + ITA",
                "Valor consolidado",
                selected_month=mes_selecionado,
            )
        display_consolidado = format_df_for_display(df_consolidado_raw)
        st.dataframe(
            style_consolidado_dataframe(display_consolidado, label_column="Conteúdo / Bloco"),
            use_container_width=True,
            height=720,
            column_config=auto_width_column_config(display_consolidado, min_width=132),
        )

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
    if output_path.is_absolute():
        return output_path
    if output_path.parent != Path("."):
        return RUNTIME_DIR / output_path
    return RUNTIME_DIR / "data" / "output" / output_path.name


def run_simulation(config: SimulationConfig) -> tuple[Path, str]:
    stdout_buffer = io.StringIO()
    output_path = resolve_output_path(config.output)
    args = argparse.Namespace(
        input_dir=str(config.input_dir), plantel=config.plantel,
        tanques=config.tanques, curvas=config.curvas, racao=config.racao,
        parametros_gerenciais=config.parametros_gerenciais,
        output=str(output_path), mostrar_erros=config.mostrar_erros,
        data_relatorio=config.data_relatorio.strftime("%d/%m/%Y"),
    )
    with redirect_stdout(stdout_buffer):
        output_path = executar(args)
    return Path(output_path), stdout_buffer.getvalue().strip()

def main() -> None:
    configure_page()
    render_header()

    data_relatorio, output_name, mostrar_erros = render_common_settings()

    render_spreadsheet_audit()

    tab_upload, tab_path = st.tabs(["📤 Upload de Arquivos", "💻 Execução Local"])
    
    uploaded_files = {}
    with tab_upload:
        col1, col2 = st.columns(2)
        with col1:
            uploaded_files["plantel"] = st.file_uploader("plantel.csv", type=["csv"], key="u_plantel")
            uploaded_files["curvas"] = st.file_uploader("curvas.csv", type=["csv"], key="u_curvas")
        with col2:
            uploaded_files["tanques"] = st.file_uploader("tanques.csv", type=["csv"], key="u_tanques")
            uploaded_files["racao"] = st.file_uploader("racao.csv", type=["csv"], key="u_racao")
        uploaded_files["parametros_gerenciais"] = st.file_uploader(
            "parametros_gerenciais.csv",
            type=["csv"],
            key="u_parametros_gerenciais",
            help="Obrigatorio. Contem dias de abate, metas PO e transferencias.",
        )
        parametros_bytes = (
            uploaded_files["parametros_gerenciais"].getvalue()
            if uploaded_files.get("parametros_gerenciais") is not None
            else None
        )
        if parametros_bytes is not None:
            uploaded_hash = hash(parametros_bytes)
            if st.session_state.get("upload_parametros_source_hash") != uploaded_hash:
                st.session_state["upload_parametros_source_hash"] = uploaded_hash
                st.session_state.pop("upload_parametros_override_bytes", None)
            parametros_bytes = st.session_state.get("upload_parametros_override_bytes", parametros_bytes)
        management_state = render_validated_management_inputs(
            data_relatorio,
            parametros_bytes,
            key_prefix="upload",
            save_path=RUNTIME_DIR / "data" / "input" / PARAMETROS_FILE,
        )

        if uploaded_files.get("curvas") is not None:
            try:
                render_curve_programs_preview(
                    curvas_cluster_dataframe_from_bytes(uploaded_files["curvas"].getvalue())
                )
            except Exception as exc:
                st.info(f"Não foi possível montar o comparativo de curvas: {exc}")
            
        missing = [f for k, f in REQUIRED_FILES.items() if uploaded_files.get(k) is None]
        if missing or management_state is None:
            if management_state is None and PARAMETROS_FILE not in missing:
                missing.append(PARAMETROS_FILE)
            st.warning("Envie todos os arquivos obrigatórios: " + ", ".join(missing))
            st.button("🚀 Executar Simulação", disabled=True, key="btn_up_disabled")
        else:
            if st.button("🚀 Executar Simulação", type="primary", key="btn_up_run"):
                try:
                    df_metas, df_terceiros, meses_visiveis = management_state
                    with tempfile.TemporaryDirectory() as temp_dir:
                        work_dir = Path(temp_dir)
                        for key, file_name in REQUIRED_FILES.items():
                            if key == "parametros_gerenciais":
                                (work_dir / file_name).write_bytes(
                                    parametros_gerenciais_to_csv(df_metas, df_terceiros)
                                )
                            else:
                                (work_dir / file_name).write_bytes(uploaded_files[key].getbuffer())
                            
                        config = SimulationConfig(
                            input_dir=work_dir, plantel=REQUIRED_FILES["plantel"],
                            tanques=REQUIRED_FILES["tanques"], curvas=REQUIRED_FILES["curvas"],
                            racao=REQUIRED_FILES["racao"],
                            parametros_gerenciais=REQUIRED_FILES["parametros_gerenciais"],
                            output=output_name,
                            data_relatorio=data_relatorio, mostrar_erros=mostrar_erros,
                        )
                        with st.spinner("Motor de Cálculo em Execução..."):
                            out_path, stdout = run_simulation(config)
                            out_bytes = out_path.read_bytes()
                            
                    st.session_state["df_metas"] = df_metas
                    st.session_state["df_terceiros"] = df_terceiros
                    st.session_state["meses_visiveis"] = meses_visiveis
                    st.session_state["last_artifact"] = ReportArtifact(out_path.name, out_bytes, stdout, str(out_path))
                except Exception as e:
                    st.error(f"Falha Crítica na Execução: {e}")

    with tab_path:
        st.caption("Modo desenvolvedor: leitura direta do diretório local.")
        raw_input_dir = Path(st.text_input("Pasta 'input'", value=r".\data\input")).expanduser()
        input_dir = raw_input_dir if raw_input_dir.is_absolute() else RUNTIME_DIR / raw_input_dir
        missing_local = [
            file_name for file_name in REQUIRED_FILES.values() if not (input_dir / file_name).exists()
        ]
        parametros_local = input_dir / REQUIRED_FILES["parametros_gerenciais"]
        management_state = None
        if parametros_local.exists():
            watch_parametros_gerenciais_file(parametros_local, key_prefix="local")
            if st.session_state.pop("local_parametros_external_update_toast", False):
                st.toast("parametros_gerenciais.csv atualizado fora do app. Tela recarregada.", icon="🔄")
            management_state = render_validated_management_inputs(
                data_relatorio,
                parametros_local.read_bytes(),
                key_prefix="local",
                save_path=parametros_local,
            )
        else:
            st.error(f"Arquivo obrigatorio nao encontrado: {PARAMETROS_FILE}")
        curvas_local = input_dir / REQUIRED_FILES["curvas"]
        if curvas_local.exists():
            try:
                render_curve_programs_preview(curvas_cluster_dataframe_from_path(curvas_local))
            except Exception as exc:
                st.info(f"Não foi possível montar o comparativo de curvas local: {exc}")
        
        if missing_local or management_state is None:
            if missing_local:
                st.warning("Arquivos locais obrigatorios ausentes: " + ", ".join(missing_local))
            st.button("🚀 Executar Simulação Local", disabled=True, key="btn_local_disabled")
        elif st.button("🚀 Executar Simulação Local", type="primary", key="btn_local_run"):
            df_metas, df_terceiros, meses_visiveis = management_state
            config = SimulationConfig(
                input_dir=input_dir, plantel=REQUIRED_FILES["plantel"],
                tanques=REQUIRED_FILES["tanques"], curvas=REQUIRED_FILES["curvas"],
                racao=REQUIRED_FILES["racao"],
                parametros_gerenciais=REQUIRED_FILES["parametros_gerenciais"],
                output=output_name,
                data_relatorio=data_relatorio, mostrar_erros=mostrar_erros,
            )
            try:
                input_dir.mkdir(parents=True, exist_ok=True)
                (input_dir / PARAMETROS_FILE).write_bytes(
                    parametros_gerenciais_to_csv(df_metas, df_terceiros)
                )
                with st.spinner("Motor de Cálculo em Execução..."):
                    out_path, stdout = run_simulation(config)
                st.session_state["df_metas"] = df_metas
                st.session_state["df_terceiros"] = df_terceiros
                st.session_state["meses_visiveis"] = meses_visiveis
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
