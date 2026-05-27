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

import streamlit as st

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from simulador_aquicola import executar


APP_TITLE = "Simulador de Planejamento Aquícola - Mar & Terra"
DEFAULT_OUTPUT = "simulacao_completa_br.csv"
BRAND_GREEN = "#17413B"
BRAND_GOLD = "#BC933F"
BRAND_GOLD_SOFT = "#E7D8B5"
LOGO_WHITE = ROOT_DIR / "app" / "assets" / "mar-terra-logo-branca.png"
LOGO_BLACK = ROOT_DIR / "app" / "assets" / "mar-terra-logo-preta.png"
REQUIRED_FILES = {
    "plantel": "plantel.csv",
    "tanques": "tanques.csv",
    "curvas": "curvas.csv",
    "racao": "racao.csv",
}


def image_data_uri(path: Path) -> str:
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


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


def configure_page() -> None:
    st.set_page_config(
        page_title="Simulador Aquícola",
        page_icon=str(LOGO_WHITE) if LOGO_WHITE.exists() else None,
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
            --control-focus: #BC933F;
        }
        .main .block-container { padding-top: 1.4rem; max-width: 1180px; }
        .hero {
            display: flex;
            align-items: center;
            gap: 1.35rem;
            padding: 1.4rem 1.55rem;
            border: 1px solid rgba(188, 147, 63, .34);
            border-radius: 10px;
            background: #17413B;
            margin-bottom: 1.25rem;
            box-shadow: 0 10px 26px rgba(23, 65, 59, .12);
        }
        .hero-logo {
            width: min(210px, 34vw);
            height: auto;
            flex: 0 0 auto;
        }
        .hero-copy { min-width: 0; }
        .hero h1 {
            margin: 0 0 .35rem 0;
            font-size: clamp(1.55rem, 3vw, 2.15rem);
            color: #FFFFFF !important;
            letter-spacing: 0;
        }
        .hero p {
            margin: 0;
            color: #E7D8B5 !important;
            font-size: 1rem;
            max-width: 760px;
        }
        div[data-testid="stWidgetLabel"] label,
        div[data-testid="stWidgetLabel"] p,
        div[data-testid="stFileUploader"] label,
        div[data-testid="stFileUploader"] p,
        .stCheckbox label,
        .stCheckbox p {
            font-weight: 600;
        }
        div[data-testid="stFileUploader"] section {
            border: 1px solid rgba(188, 147, 63, .45);
            border-radius: 8px;
        }
        div[data-testid="stFileUploader"] button {
            border-color: rgba(188, 147, 63, .55);
        }
        .stButton > button {
            width: 100%;
            min-height: 3rem;
            font-weight: 700;
            border-radius: 8px;
            border-color: #BC933F;
            background: #17413B;
            color: #FFFFFF !important;
        }
        .stButton > button p,
        .stDownloadButton > button p {
            color: inherit !important;
        }
        .stButton > button:disabled,
        .stButton > button:disabled:hover {
            border-color: #D8C99B;
            background: #D8C99B;
            color: #17413B !important;
            opacity: 1;
        }
        .stButton > button:hover,
        .stDownloadButton > button:hover {
            border-color: #A97F2E;
            background: #102F2B;
            color: #FFFFFF !important;
        }
        .stButton > button:focus,
        .stDownloadButton > button:focus {
            outline: 3px solid #BC933F;
            outline-offset: 2px;
            box-shadow: none;
        }
        .stDownloadButton > button {
            width: 100%;
            min-height: 3rem;
            font-weight: 700;
            border-radius: 8px;
            border-color: #BC933F;
            background: #17413B;
            color: #FFFFFF !important;
        }
        div[data-testid="stTabs"] button[aria-selected="true"] {
            border-bottom-color: #BC933F;
        }
        section[data-testid="stSidebar"] {
            border-right: 1px solid rgba(188, 147, 63, .28);
        }
        h2, h3 {
            letter-spacing: 0;
        }
        .report-card-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: .9rem;
            margin-top: .75rem;
            align-items: start;
        }
        .report-card {
            border: 1px solid rgba(188, 147, 63, .42);
            border-radius: 8px;
            padding: 1rem;
            background: rgba(188, 147, 63, .08);
        }
        .report-card h3 {
            margin: 0 0 .25rem 0;
            font-size: 1.05rem;
        }
        .report-card .muted {
            opacity: .78;
            font-size: .88rem;
            margin-bottom: .85rem;
        }
        .report-card-kpis {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: .7rem;
        }
        .report-card-kpis strong {
            display: block;
            font-size: .82rem;
            opacity: .72;
            margin-bottom: .1rem;
        }
        .report-card-kpis span {
            font-size: 1rem;
            font-weight: 700;
        }
        .status-pill {
            display: inline-block;
            margin-top: .85rem;
            padding: .25rem .55rem;
            border: 1px solid rgba(188, 147, 63, .55);
            border-radius: 999px;
            font-size: .82rem;
            font-weight: 700;
        }
        @media (max-width: 760px) {
            .hero { align-items: flex-start; flex-direction: column; }
            .hero-logo { width: 190px; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_header() -> None:
    logo_markup = ""
    if LOGO_WHITE.exists():
        logo_markup = f'<img class="hero-logo" src="{image_data_uri(LOGO_WHITE)}" alt="Mar & Terra">'

    st.markdown(
        f"""
        <div class="hero">
            {logo_markup}
            <div class="hero-copy">
                <h1 style="color:#FFFFFF !important;">{APP_TITLE}</h1>
                <p style="color:#E7D8B5 !important;">
                    Projete o crescimento de lotes de peixes, consumo de ração,
                    custos, biomassa, mortalidade e marcos de manejo a partir dos
                    arquivos operacionais do simulador.
                </p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def sanitize_output_name(value: str) -> str:
    output = value.strip() or DEFAULT_OUTPUT
    return output if output.lower().endswith(".csv") else f"{output}.csv"


def save_uploaded_files(uploaded_files: dict[str, object], target_dir: Path) -> None:
    for key, file_name in REQUIRED_FILES.items():
        uploaded = uploaded_files[key]
        destination = target_dir / file_name
        destination.write_bytes(uploaded.getbuffer())


def build_namespace(config: SimulationConfig) -> argparse.Namespace:
    return argparse.Namespace(
        input_dir=str(config.input_dir),
        plantel=config.plantel,
        tanques=config.tanques,
        curvas=config.curvas,
        racao=config.racao,
        output=config.output,
        mostrar_erros=config.mostrar_erros,
        data_relatorio=config.data_relatorio.strftime("%d/%m/%Y"),
    )


def run_simulation(config: SimulationConfig) -> tuple[Path, str]:
    stdout_buffer = io.StringIO()
    args = build_namespace(config)
    with redirect_stdout(stdout_buffer):
        output_path = executar(args)
    return Path(output_path), stdout_buffer.getvalue().strip()


def read_csv_rows_from_bytes(data: bytes, limit: int | None = None) -> list[dict[str, str]]:
    text = data.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text), delimiter=";")
    if limit is None:
        return list(reader)
    return [row for _, row in zip(range(limit), reader)]


def read_csv_preview(path: Path, limit: int = 50) -> list[dict[str, str]]:
    return read_csv_rows_from_bytes(path.read_bytes(), limit=limit)


def parse_br_number(value: object) -> float:
    if value is None:
        return 0.0
    text = str(value).strip()
    if not text:
        return 0.0
    normalized = text.replace("%", "").replace("R$", "").strip()
    if "," in normalized:
        normalized = normalized.replace(".", "").replace(",", ".")
    else:
        normalized = normalized.replace(".", "")
    try:
        return float(normalized)
    except ValueError:
        return 0.0


def parse_report_date(value: object) -> datetime:
    text = str(value or "").strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return datetime.min


def format_br_number(value: float, decimals: int = 2) -> str:
    formatted = f"{value:,.{decimals}f}"
    return formatted.replace(",", "X").replace(".", ",").replace("X", ".")


def latest_rows_by_lot(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    latest: dict[tuple[str, str], dict[str, str]] = {}
    for row in rows:
        key = (row.get("Produtor", ""), row.get("Tanque", ""))
        current = latest.get(key)
        if current is None or parse_report_date(row.get("Data")) >= parse_report_date(current.get("Data")):
            latest[key] = row
    return sorted(latest.values(), key=lambda item: (item.get("Regiao", ""), item.get("Produtor", ""), item.get("Tanque", "")))


def is_ready_for_harvest(row: dict[str, str]) -> bool:
    status = row.get("Status", "").strip().lower()
    peso = parse_br_number(row.get("Peso Medio (g)"))
    return status == "peixe pronto" or peso >= 900


def render_download(output_path: Path) -> None:
    data = output_path.read_bytes()
    st.download_button(
        label="⬇️ Baixar CSV gerado",
        data=data,
        file_name=output_path.name,
        mime="text/csv",
        use_container_width=True,
    )


def render_preview(output_path: Path) -> None:
    preview = read_csv_preview(output_path, limit=50)
    if not preview:
        st.info("O arquivo foi gerado, mas não possui linhas para pré-visualização.")
        return

    st.subheader("Prévia do relatório")
    st.caption("Primeiras 50 linhas do CSV gerado.")
    st.dataframe(preview, use_container_width=True, hide_index=True)


def render_table_view(rows: list[dict[str, str]]) -> None:
    st.subheader("Tabela completa")
    st.caption("Visualização tabular do CSV gerado.")
    st.dataframe(rows, use_container_width=True, hide_index=True)


def render_card_view(rows: list[dict[str, str]]) -> None:
    latest = latest_rows_by_lot(rows)
    if not latest:
        st.info("Não há dados suficientes para montar os cards.")
        return

    st.subheader("Cards por tanque")
    st.caption("Cada card mostra o último registro projetado de cada produtor/tanque.")

    status_filter = st.selectbox(
        "Filtro dos cards",
        ["Todos", "Somente Peixe Pronto", "Somente com marcador"],
        key="card_status_filter",
    )
    if status_filter == "Somente Peixe Pronto":
        latest = [row for row in latest if is_ready_for_harvest(row)]
    elif status_filter == "Somente com marcador":
        latest = [row for row in latest if row.get("Status", "").strip()]

    if not latest:
        st.info("Nenhum tanque encontrado para o filtro selecionado.")
        return

    limit = st.slider("Quantidade de cards na tela", 6, 60, min(24, max(6, len(latest))), 6, key="card_limit")
    visible_rows = latest[:limit]

    cards = []
    for row in visible_rows:
        title = f"{row.get('Produtor', '')} - Tanque {row.get('Tanque', '')}"
        subtitle = f"{row.get('Regiao', '')} | {row.get('Classe', '')} | {row.get('Data', '')}"
        status = row.get("Status", "").strip() or "Sem marcador"
        card = (
            '<div class="report-card">'
            f"<h3>{html.escape(title)}</h3>"
            f'<div class="muted">{html.escape(subtitle)}</div>'
            '<div class="report-card-kpis">'
            f'<div><strong>Peso médio</strong><span>{html.escape(row.get("Peso Medio (g)", ""))} g</span></div>'
            f'<div><strong>Biomassa</strong><span>{html.escape(row.get("Biomassa (kg)", ""))} kg</span></div>'
            f'<div><strong>Peixes</strong><span>{html.escape(row.get("Quantidade de Peixes", ""))}</span></div>'
            f'<div><strong>Ração acum.</strong><span>{html.escape(row.get("Consumo de Racao Acumulado (kg)", ""))} kg</span></div>'
            f'<div><strong>Custo acum.</strong><span>R$ {html.escape(row.get("Custo de Racao Acumulado", ""))}</span></div>'
            f'<div><strong>TCA acum.</strong><span>{html.escape(row.get("TCA Acumulado", ""))}</span></div>'
            "</div>"
            f'<span class="status-pill">{html.escape(status)}</span>'
            "</div>"
        )
        cards.append(card)

    cards_html = f'<div class="report-card-grid">{"".join(cards)}</div>'
    if hasattr(st, "html"):
        st.html(cards_html)
    else:
        st.markdown(cards_html, unsafe_allow_html=True)
    if len(latest) > len(visible_rows):
        st.caption(f"Mostrando {len(visible_rows)} de {len(latest)} tanques. Aumente o limite para ver mais cards.")


def build_excel_style_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    ready_by_lot_month: dict[tuple[str, str, str, str], dict[str, str]] = {}
    for row in rows:
        if not is_ready_for_harvest(row):
            continue
        data = parse_report_date(row.get("Data"))
        if data == datetime.min:
            continue
        month_key = data.strftime("%Y-%m")
        lot_key = (row.get("Produtor", ""), row.get("Tanque", ""), month_key, row.get("Regiao", ""))
        current = ready_by_lot_month.get(lot_key)
        if current is None or parse_report_date(row.get("Data")) < parse_report_date(current.get("Data")):
            ready_by_lot_month[lot_key] = row

    grouped: dict[tuple[str, str, str], dict[str, float]] = defaultdict(
        lambda: {"biomassa": 0.0, "peixes": 0.0, "tanques": 0.0}
    )
    months = set()
    for row in ready_by_lot_month.values():
        data = parse_report_date(row.get("Data"))
        month_key = data.strftime("%Y-%m")
        months.add(month_key)
        key = (row.get("Regiao", "") or "Sem região", row.get("Classe", "") or "Sem classe", month_key)
        grouped[key]["biomassa"] += parse_br_number(row.get("Biomassa (kg)"))
        grouped[key]["peixes"] += parse_br_number(row.get("Quantidade de Peixes"))
        grouped[key]["tanques"] += 1

    sorted_months = sorted(months)
    regions_classes = sorted({(region, classe) for region, classe, _ in grouped})
    table_rows = []
    for region, classe in regions_classes:
        biomass_row = {"Região": region, "Classe": classe, "Indicador": "Biomassa disponível para abate (kg)"}
        tank_row = {"Região": region, "Classe": classe, "Indicador": "Tanques prontos"}
        fish_row = {"Região": region, "Classe": classe, "Indicador": "Peixes disponíveis"}
        for month in sorted_months:
            metrics = grouped.get((region, classe, month), {})
            biomass_row[month] = format_br_number(metrics.get("biomassa", 0.0), 2)
            tank_row[month] = format_br_number(metrics.get("tanques", 0.0), 0)
            fish_row[month] = format_br_number(metrics.get("peixes", 0.0), 0)
        table_rows.extend([biomass_row, tank_row, fish_row])
    return table_rows


def render_excel_style_view(rows: list[dict[str, str]]) -> None:
    st.subheader("Painel estilo Excel")
    st.caption("Resumo mensal de disponibilidade para abate, inspirado no arquivo de projeção enviado.")
    table_rows = build_excel_style_rows(rows)
    if not table_rows:
        st.info("Ainda não há linhas com Peixe Pronto ou peso médio igual/superior a 900g para montar o painel.")
        return
    st.dataframe(table_rows, use_container_width=True, hide_index=True)


def render_report_views(data: bytes) -> None:
    rows = read_csv_rows_from_bytes(data)
    if not rows:
        st.info("O arquivo foi gerado, mas não possui linhas para visualização.")
        return

    st.divider()
    st.subheader("Visualização do relatório")
    view = st.segmented_control(
        "Escolha como deseja visualizar o resultado",
        ["Tabela completa", "Cards por tanque", "Painel estilo Excel"],
        default="Tabela completa",
        key="report_view_mode",
    )
    view = view or "Tabela completa"

    if view == "Tabela completa":
        render_table_view(rows[:500])
        if len(rows) > 500:
            st.caption(f"Mostrando as primeiras 500 linhas de {len(rows)}. O CSV baixado contém o relatório completo.")
    elif view == "Cards por tanque":
        render_card_view(rows)
    else:
        render_excel_style_view(rows)


def render_upload_inputs() -> dict[str, object]:
    st.subheader("Arquivos de entrada")
    col1, col2 = st.columns(2)
    with col1:
        plantel = st.file_uploader("plantel.csv", type=["csv"], key="upload_plantel")
        curvas = st.file_uploader("curvas.csv", type=["csv"], key="upload_curvas")
    with col2:
        tanques = st.file_uploader("tanques.csv", type=["csv"], key="upload_tanques")
        racao = st.file_uploader("racao.csv", type=["csv"], key="upload_racao")

    return {
        "plantel": plantel,
        "tanques": tanques,
        "curvas": curvas,
        "racao": racao,
    }


def missing_uploads(uploaded_files: dict[str, object]) -> list[str]:
    return [file_name for key, file_name in REQUIRED_FILES.items() if uploaded_files[key] is None]


def render_common_settings() -> tuple[date, str, bool]:
    st.subheader("Configurações da simulação")
    col1, col2, col3 = st.columns([1, 1.3, 1])
    with col1:
        data_relatorio = st.date_input("Data do relatório", value=date.today(), format="DD/MM/YYYY")
    with col2:
        output_name = st.text_input("Arquivo de saída", value=DEFAULT_OUTPUT)
    with col3:
        mostrar_erros = st.checkbox("Mostrar erros de inconsistência", value=False)
    return data_relatorio, sanitize_output_name(output_name), mostrar_erros


def render_path_mode(data_relatorio: date, output_name: str, mostrar_erros: bool) -> SimulationConfig:
    st.subheader("Pasta com os CSVs")
    default_input_dir = ROOT_DIR / "data" / "input"
    input_dir = Path(st.text_input("Pasta de entrada", value=str(default_input_dir))).expanduser()

    col1, col2 = st.columns(2)
    with col1:
        plantel = st.text_input("Nome do plantel", value=REQUIRED_FILES["plantel"])
        curvas = st.text_input("Nome das curvas", value=REQUIRED_FILES["curvas"])
    with col2:
        tanques = st.text_input("Nome dos tanques", value=REQUIRED_FILES["tanques"])
        racao = st.text_input("Nome da ração", value=REQUIRED_FILES["racao"])

    return SimulationConfig(
        input_dir=input_dir,
        plantel=plantel.strip(),
        tanques=tanques.strip(),
        curvas=curvas.strip(),
        racao=racao.strip(),
        output=output_name,
        data_relatorio=data_relatorio,
        mostrar_erros=mostrar_erros,
    )


def validate_local_files(config: SimulationConfig) -> list[str]:
    missing = []
    for file_name in [config.plantel, config.tanques, config.curvas, config.racao]:
        if not (config.input_dir / file_name).exists():
            missing.append(str(config.input_dir / file_name))
    return missing


def store_report_artifact(artifact: ReportArtifact) -> None:
    st.session_state["last_report_artifact"] = artifact


def render_report_result(artifact: ReportArtifact) -> None:
    st.success(f"Simulação concluída: {artifact.file_name}")
    if artifact.captured_output:
        with st.expander("Log da execução"):
            st.code(artifact.captured_output, language="text")

    col1, col2 = st.columns([1, 2])
    with col1:
        st.download_button(
            label="⬇️ Baixar CSV gerado",
            data=artifact.output_bytes,
            file_name=artifact.file_name,
            mime="text/csv",
            use_container_width=True,
            key="download_generated_report",
        )
    with col2:
        if artifact.output_path:
            st.info(f"Arquivo salvo em: `{artifact.output_path}`")
        else:
            st.info("Arquivo gerado a partir dos CSVs enviados por upload.")

    render_report_views(artifact.output_bytes)


def render_execution_button(config: SimulationConfig) -> None:
    if st.button("🚀 Executar Simulação", type="primary", key="run_local_path"):
        missing = validate_local_files(config)
        if missing:
            st.error("Arquivos não encontrados:\n\n" + "\n".join(f"- {path}" for path in missing))
            return

        try:
            with st.spinner("Processando simulação. Isso pode levar alguns segundos..."):
                output_path, captured_output = run_simulation(config)
            store_report_artifact(
                ReportArtifact(
                    file_name=output_path.name,
                    output_bytes=output_path.read_bytes(),
                    captured_output=captured_output,
                    output_path=str(output_path),
                )
            )
        except Exception as exc:
            st.error("Não foi possível executar a simulação.")
            with st.expander("Detalhes técnicos do erro"):
                st.exception(exc)


def render_upload_execution(
    uploaded_files: dict[str, object],
    data_relatorio: date,
    output_name: str,
    mostrar_erros: bool,
) -> None:
    missing = missing_uploads(uploaded_files)
    if missing:
        st.warning("Envie todos os arquivos obrigatórios: " + ", ".join(missing))
        st.button("🚀 Executar Simulação", type="primary", disabled=True, key="run_upload_disabled")
        return

    if st.button("🚀 Executar Simulação", type="primary", key="run_upload_files"):
        try:
            with tempfile.TemporaryDirectory(prefix="simulador_aquicola_") as temp_dir:
                work_dir = Path(temp_dir)
                save_uploaded_files(uploaded_files, work_dir)
                config = SimulationConfig(
                    input_dir=work_dir,
                    plantel=REQUIRED_FILES["plantel"],
                    tanques=REQUIRED_FILES["tanques"],
                    curvas=REQUIRED_FILES["curvas"],
                    racao=REQUIRED_FILES["racao"],
                    output=output_name,
                    data_relatorio=data_relatorio,
                    mostrar_erros=mostrar_erros,
                )
                with st.spinner("Processando simulação. Isso pode levar alguns segundos..."):
                    output_path, captured_output = run_simulation(config)
                    output_bytes = output_path.read_bytes()
            store_report_artifact(
                ReportArtifact(
                    file_name=Path(output_name).name,
                    output_bytes=output_bytes,
                    captured_output=captured_output,
                    output_path=None,
                )
            )
        except Exception as exc:
            st.error("Não foi possível executar a simulação.")
            with st.expander("Detalhes técnicos do erro"):
                st.exception(exc)


def main() -> None:
    configure_page()
    render_header()

    with st.sidebar:
        if LOGO_BLACK.exists():
            st.image(str(LOGO_BLACK), use_container_width=True)
        st.header("Como usar")
        st.markdown(
            """
            1. Envie os 4 CSVs ou informe uma pasta local.
            2. Escolha a data do relatório.
            3. Defina o nome de saída.
            4. Execute e baixe o CSV gerado.
            """
        )

    data_relatorio, output_name, mostrar_erros = render_common_settings()

    tab_upload, tab_path = st.tabs(["Upload de arquivos", "Pasta local"])
    with tab_upload:
        uploaded_files = render_upload_inputs()
        render_upload_execution(uploaded_files, data_relatorio, output_name, mostrar_erros)

    with tab_path:
        config = render_path_mode(data_relatorio, output_name, mostrar_erros)
        render_execution_button(config)

    artifact = st.session_state.get("last_report_artifact")
    if artifact:
        render_report_result(artifact)


if __name__ == "__main__":
    main()
