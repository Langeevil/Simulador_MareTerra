from __future__ import annotations

import argparse
import base64
import csv
import html
import io
import sys
import tempfile
from collections import defaultdict
from contextlib import redirect_stdout
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import streamlit as st

# Configuração de Paths do Sistema
ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# Tentativa de importação do motor da simulação
try:
    from simulador_aquicola import executar
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
            'data': 'data'
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

        return df
    except Exception as e:
        st.error(f"Falha ao ler dados gerados: {str(e)}")
        return pd.DataFrame()

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
            c, p, m, v = row['Classe'], row['Produtor'], row['Mês'], float(row.get('Volume (kg)', 0))
            if m in months and pd.notna(v):
                block_data[(c, p)][m] += v
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
    abate_po = {m: float(df_metas.loc[df_metas['Mês'] == m, f'PO {region} (kg)'].values[0]) for m in months}

    for label, data_dict in prevs.items():
        output_rows.append({"Conteúdo / Bloco": label, **data_dict})
    output_rows.append({"Conteúdo / Bloco": "Previsão Disponibilidade Total", **prev_total})
    output_rows.append({"Conteúdo / Bloco": "Abate PO Atualizado Total Mês", **abate_po})
    output_rows.append({col: "" for col in ["Conteúdo / Bloco"] + months})

    # Bloco: Disponibilidade por Dia
    output_rows.append({"Conteúdo / Bloco": f"QUADRO DE DISPONIBILIDADE PARA O ABATE POR DIA - {region}", **{m: "" for m in months}})
    
    dias_abate = {m: max(1.0, float(df_metas.loc[df_metas['Mês'] == m, f'Dias Abate {region}'].values[0])) for m in months}
    output_rows.append({"Conteúdo / Bloco": "Dias de Abate", **dias_abate})
    
    kg_dia_total = {m: prev_total[m] / dias_abate[m] for m in months}
    output_rows.append({"Conteúdo / Bloco": "Kg/Dia Próprio", **{m: prevs["Previsão de Abate Próprio"][m] / dias_abate[m] for m in months}})
    output_rows.append({"Conteúdo / Bloco": "Kg/Dia Integração", **{m: prevs["Previsão de Abate Integração"][m] / dias_abate[m] for m in months}})
    output_rows.append({"Conteúdo / Bloco": "Kg/Dia Parceria", **{m: prevs["Previsão de Abate Parceria"][m] / dias_abate[m] for m in months}})
    output_rows.append({"Conteúdo / Bloco": "Total Kg/Dia Disponível Abate", **kg_dia_total})
    output_rows.append({col: "" for col in ["Conteúdo / Bloco"] + months})

    # Bloco: Saldos
    output_rows.append({"Conteúdo / Bloco": f"QUADRO DO SALDO DA DISPONIBILIDADE PARA O ABATE POR DIA e POR MÊS - {region}", **{m: "" for m in months}})
    
    po_atualizado_dia = {m: abate_po[m] / dias_abate[m] for m in months}
    saldo_dia = {m: kg_dia_total[m] - po_atualizado_dia[m] for m in months}
    
    output_rows.append({"Conteúdo / Bloco": "PO Atualizado", **po_atualizado_dia})
    output_rows.append({"Conteúdo / Bloco": "Saldo Atualizado / dia", **saldo_dia})
    
    saldo_acm = {}
    running_acm = 0.0
    for m in months:
        running_acm += (saldo_dia[m] * dias_abate[m])
        saldo_acm[m] = running_acm
        
    output_rows.append({"Conteúdo / Bloco": "Saldo Acm Atualizado / mês", **saldo_acm})

    return pd.DataFrame(output_rows)

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
    """Aplica máscara visual em DataFrames sem alterar a base de cálculo."""
    display_df = df.copy()
    for col in display_df.columns:
        if col == "Conteúdo / Bloco": continue
        
        formatted_col = []
        for _, row in display_df.iterrows():
            v = row[col]
            lbl = str(row["Conteúdo / Bloco"])
            
            if pd.isna(v) or v == "":
                formatted_col.append("")
            elif lbl == "Dias de Abate":
                formatted_col.append(f"{int(float(v))}")
            else:
                formatted_col.append(format_br_number(v, 2))
                
        display_df[col] = formatted_col
    return display_df

def export_to_excel(df_apt: pd.DataFrame, df_ita: pd.DataFrame) -> bytes:
    """Gera o binário Excel com múltiplas abas."""
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df_apt.to_excel(writer, sheet_name="APT", index=False)
        df_ita.to_excel(writer, sheet_name="ITA", index=False)
    return buffer.getvalue()

# ==========================================
# CONTROLES INTERATIVOS DO STREAMLIT
# ==========================================

def render_management_inputs(data_inicio: date, num_meses: int = 12) -> tuple[pd.DataFrame, pd.DataFrame]:
    st.divider()
    st.subheader("📊 Parâmetros Gerenciais e Metas")
    st.caption("Insira e ajuste as metas comerciais, dias operacionais e volumes extras antes de simular.")
    
    meses = pd.date_range(data_inicio, periods=num_meses, freq='MS').strftime("%Y-%m").tolist()
        
    col1, col2 = st.columns([1.1, 0.9])
    
    with col1:
        st.markdown("#### 1. Metas (PO) e Dias de Abate por Região")
        df_metas_base = pd.DataFrame({
            "Mês": meses,
            "Dias Abate APT": [21] * num_meses,
            "PO APT (kg)": [90000] * num_meses,
            "Dias Abate ITA": [21] * num_meses,
            "PO ITA (kg)": [45000] * num_meses,
        })
        df_metas_editado = st.data_editor(df_metas_base, use_container_width=True, hide_index=True, key="metas_editor")

    with col2:
        st.markdown("#### 2. Volumes de Terceiros e Transferências")
        df_terceiros_base = pd.DataFrame(columns=["Região Destino", "Classe", "Produtor", "Mês", "Volume (kg)"])
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
            key="terceiros_editor"
        )
        
    return df_metas_editado, df_terceiros_editado

# ==========================================
# GERAÇÃO DO DASHBOARD E INTERFACE PRINCIPAL
# ==========================================

def render_excel_style_view(csv_bytes: bytes) -> None:
    st.subheader("📋 Relatório Corporativo de Projeção de Abate")
    st.caption("Visões estruturadas por blocos e regiões (Idêntico ao modelo Excel de controle).")
    
    df_metas = st.session_state.get("df_metas")
    df_terceiros = st.session_state.get("df_terceiros")
    
    if df_metas is None:
        st.warning("Preencha as configurações de parâmetros gerenciais no topo da página.")
        return
        
    with st.spinner("Processando base de dados com Pandas..."):
        df_base = clean_and_prepare_dataframe(csv_bytes)
        
        if df_base.empty:
            st.error("Falha ao analisar a base de dados. Verifique a estrutura do CSV gerado.")
            return

        df_apt_raw = process_regional_data(df_base, "APT", df_metas, df_terceiros)
        df_ita_raw = process_regional_data(df_base, "ITA", df_metas, df_terceiros)
    
    excel_bytes = export_to_excel(df_apt_raw, df_ita_raw)
    
    st.download_button(
        label="📥 Baixar Relatório Gerencial em Excel (.xlsx)",
        data=excel_bytes,
        file_name="Projeção_Abate_Geral_Gerado.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )
    
    tab_apt, tab_ita = st.tabs(["Aba APT (Aparecida do Taboado)", "Aba ITA (Itaporã)"])
    with tab_apt:
        st.dataframe(format_df_for_display(df_apt_raw), use_container_width=True, hide_index=True, height=550)
    with tab_ita:
        st.dataframe(format_df_for_display(df_ita_raw), use_container_width=True, hide_index=True, height=550)

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

def run_simulation(config: SimulationConfig) -> tuple[Path, str]:
    stdout_buffer = io.StringIO()
    args = argparse.Namespace(
        input_dir=str(config.input_dir), plantel=config.plantel,
        tanques=config.tanques, curvas=config.curvas, racao=config.racao,
        output=config.output, mostrar_erros=config.mostrar_erros,
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
    df_metas, df_terceiros = render_management_inputs(data_relatorio, num_meses=12)
    st.session_state["df_metas"] = df_metas
    st.session_state["df_terceiros"] = df_terceiros

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
                            
                    st.session_state["last_artifact"] = ReportArtifact(Path(output_name).name, out_bytes, stdout, None)
                except Exception as e:
                    st.error(f"Falha Crítica na Execução: {e}")

    with tab_path:
        st.caption("Modo desenvolvedor: leitura direta do diretório local.")
        input_dir = Path(st.text_input("Pasta 'input'", value=str(ROOT_DIR / "data" / "input"))).expanduser()
        
        if st.button("🚀 Executar Simulação Local", type="primary", key="btn_local_run"):
            config = SimulationConfig(
                input_dir=input_dir, plantel=REQUIRED_FILES["plantel"],
                tanques=REQUIRED_FILES["tanques"], curvas=REQUIRED_FILES["curvas"],
                racao=REQUIRED_FILES["racao"], output=output_name,
                data_relatorio=data_relatorio, mostrar_erros=mostrar_erros,
            )
            try:
                with st.spinner("Motor de Cálculo em Execução..."):
                    out_path, stdout = run_simulation(config)
                st.session_state["last_artifact"] = ReportArtifact(out_path.name, out_path.read_bytes(), stdout, str(out_path))
            except Exception as e:
                st.error(f"Falha Crítica na Execução: {e}")

    # Renderização Condicional do Relatório Gerado
    artifact = st.session_state.get("last_artifact")
    if artifact:
        st.success("✅ Simulação e Processamento de Dados concluídos com sucesso!")
        st.divider()
        render_excel_style_view(artifact.output_bytes)

if __name__ == "__main__":
    main()