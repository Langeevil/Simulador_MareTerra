from __future__ import annotations

import argparse
import bisect
import csv
import math
import re
import sys
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


PESO_DESPESCA_G = 900.0
LIMITE_DIAS = 730
FATOR_AJUSTE_PEIXE_PRONTO = 0.84
MARCADOR_PEIXE_PRONTO = "pronto"
VAZIO_SANITARIO_DIAS = 5


SAIDA_COLUNAS = [
    "Produtor",
    "Tanque",
    "Data",
    "Semana",
    "Quantidade de Peixes",
    "Peso Medio (g)",
    "Biomassa (kg)",
    "Tipo de Ração",
    "Consumo de Racao Diario (kg)",
    "Consumo de Racao na Fase (kg)",
    # "Consumo de Racao Acumulado (kg)",
    "Custo de Racao Diario",
    "Custo de Racao Acumulado",
    # "Ganho de Biomassa Acumulado (kg)",
    "TCA Diario",
    "TCA Acumulado",
    "GDP Diario (g/dia)",
    "GDP Acumulado (g)",
    "Mortalidade Diaria (peixes)",
    "Mortalidade Acumulada (peixes)",
    "Sobrevivencia Diaria (%)",
    "Sobrevivencia Acumulada (%)",
    "Status",
    "Regiao",
    "Classe",
    "Tanques Liberados",
    "Tanques Disponivel",
]


def runtime_root() -> Path:
    """Raiz usada para caminhos relativos, tanto em dev quanto no executavel."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def resolve_runtime_path(caminho: str | Path) -> Path:
    path = Path(caminho).expanduser()
    if path.is_absolute():
        return path
    return runtime_root() / path


def resolve_input_file(input_dir: Path, arquivo: str | Path) -> Path:
    path = Path(arquivo).expanduser()
    if path.is_absolute():
        return path
    if path.parent != Path("."):
        return resolve_runtime_path(path)
    return input_dir / path


ALIASES_PLANTEL = {
    "produtor": ["produtor", "proprietario", "cliente", "fazenda"],
    "tanque": ["tanque", "id tanque", "tanque id", "estrutura", "viveiro"],
    "regiao": ["regiao", "regiao produtor", "localidade", "area"],
    "classe": ["classe", "classificacao", "tipo", "categoria"],
    "cluster": [
        "cluster",
        "perfil",
        "perfil produtor",
        "perfil de produtor",
        "perfil tecnologico",
        "tecnologia",
        "nivel tecnologico",
    ],
    "quantidade": [
        "quantidade de peixes",
        "quantidade inicial de peixes",
        "quantidade",
        "saldo final",
        "qtd peixes",
        "qtd",
        "q",
        "peixes",
        "numero de peixes",
    ],
    "peso_medio": [
        "peso medio atual",
        "peso medio",
        "peso medio g",
        "peso medio (g)",
        "ultima pesagem g",
        "ult pesagem g",
        "pm atual",
        "pm",
        "peso atual",
        "peso",
    ],
    "data_alojamento": [
        "data de alojamento",
        "data alojamento",
        "alojamento",
        "dt ult biometria",
        "dt ultima biometria",
        "ultima biometria",
        "data entrada",
        "data de entrada",
        "data inicio",
        "inicio",
    ],
}


ALIASES_CURVAS = {
    "dia": ["dia", "dia ciclo", "dia_ciclo", "dc", "dias", "idade"],
    "regiao": ["regiao", "região", "localidade", "polo"],
    "estacao": ["estacao", "sazonalidade", "periodo", "epoca"],
    "cluster": [
        "cluster",
        "perfil",
        "perfil produtor",
        "perfil de produtor",
        "perfil tecnologico",
        "tecnologia",
        "nivel tecnologico",
    ],
    "peso_ref": [
        "peso medio",
        "peso medio g",
        "peso medio (g)",
        "peso tabelado",
        "peso referencia",
        "peso ref",
        "pm",
        "peso",
    ],
    "gdp": [
        "gdp",
        "ganho de peso diario",
        "ganho diario",
        "ganho peso diario",
        "crescimento diario",
    ],
    "mortalidade_pct": [
        "mortalidade",
        "mortalidade diaria",
        "mortalidade pct",
        "mortalidade %",
        "mortalidade (%)",
        "m pct",
        "m_pct",
    ],
        "pv_pct": [
        "pv",
        "pv pct",
        "pv %",
        "pv (%)",
        "peso vivo",
        "taxa pv",
        "taxa de peso vivo",
        "arraçoamento",
        "arrazoamento",
    ],
    "racao_und": [
        "qtd racao und",
        "racao und",
        "racao/peixe",
        "consumo peixe",
        "qtd racao",
    ],
    "marco": [
        "marco",
        "marco de gestao",
        "marco de gestao verao",
        "marco de gestao inverno",
        "marcador",
        "status curva",
    ],
}


ALIASES_TANQUES = {
    "tanque": ["tanque", "id tanque", "tanque id", "estrutura", "viveiro"],
    "regiao": ["regiao", "regiao produtor", "localidade", "area"],
    "classe": ["classe", "classificacao", "tipo", "categoria"],
}


PARAMETROS_GERENCIAIS_REQUIRED_COLUMNS = {
    "base": {"tipo", "mes", "regiao"},
    "abate": {"dias_abate"},
    "metas": {"po_diario_kg"},
    "transferencias": {"classe", "produtor", "volume_kg"},
}

PARAMETROS_GERENCIAIS_TIPOS = {
    "abate": {"abate", "dia_abate", "dias_abate"},
    "metas": {"meta", "metas", "meta_po", "metas_po"},
    "transferencias": {"transferencia", "transferencias"},
}


ALIASES_RACAO = {
    "peso_inicial": [
        "peso medio inicial",
        "peso_medio_inicial",
        "peso inicial",
        "pm inicial",
        "inicio",
    ],
    "peso_final": [
        "peso medio final",
        "peso_medio_final",
        "peso final",
        "pm final",
        "fim",
    ],
    "preco_kg": ["preco kg", "preco_kg", "preco", "valor kg", "custo kg"],
    "fase": ["fase", "fase nutricional", "fase produtiva", "tipo de racao", "tipo racao", "racao", "fase de producao"],
}


@dataclass(frozen=True)
class CsvTable:
    headers: list[str]
    rows: list[dict[str, str]]


@dataclass(frozen=True)
class Lote:
    produtor: str
    tanque: str
    regiao: str
    classe: str
    cluster: str
    quantidade: float
    peso_medio_g: float
    data_alojamento: date


@dataclass(frozen=True)
class FaixaRacao:
    peso_inicial_g: float
    peso_final_g: float
    preco_kg: float
    fase: str


Curva = dict[str, float | int | str]


def normalizar_nome(valor: object) -> str:
    texto = unicodedata.normalize("NFKD", str(valor))
    texto = "".join(ch for ch in texto if not unicodedata.combining(ch))
    texto = texto.lower().strip()
    texto = re.sub(r"[^a-z0-9]+", " ", texto)
    texto = re.sub(r"\s+", " ", texto)
    return texto.strip()


def mapa_colunas(headers: Iterable[str]) -> dict[str, str]:
    return {normalizar_nome(col): col for col in headers}


def encontrar_coluna(
    headers: Iterable[str],
    aliases: Iterable[str],
    *,
    obrigatoria: bool = True,
    contexto: str = "arquivo",
) -> str | None:
    colunas = mapa_colunas(headers)
    for alias in aliases:
        nome = normalizar_nome(alias)
        if nome in colunas:
            return colunas[nome]

    if obrigatoria:
        esperado = ", ".join(aliases)
        raise ValueError(f"Coluna obrigatoria ausente em {contexto}. Esperado: {esperado}")
    return None


def parse_numero_br(valor: object) -> float:
    if valor is None:
        return math.nan
    if isinstance(valor, (int, float)):
        return float(valor)

    texto = str(valor).strip()
    if not texto or texto.lower() in {"nan", "none", "null", "-"}:
        return math.nan

    texto = texto.replace("%", "").replace(" ", "")
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    else:
        texto = texto.replace(",", ".")

    try:
        return float(texto)
    except ValueError:
        return math.nan


def normalizar_taxa_pv(valor: object) -> float:
    taxa = float(valor)
    return taxa / 100.0 if taxa > 1.0 else taxa


def parse_data_br(valor: object) -> date:
    texto = str(valor).strip()
    if not texto:
        raise ValueError("data vazia")

    formatos = ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d", "%d-%m-%Y", "%d.%m.%Y")
    for formato in formatos:
        try:
            return datetime.strptime(texto, formato).date()
        except ValueError:
            pass

    raise ValueError(f"data invalida: {texto}")


def detectar_estacao(data_ref: date) -> str:
    return "V" if data_ref.month in {11, 12, 1, 2, 3, 4, 5} else "I"


def normalizar_estacao(valor: object) -> str:
    texto = normalizar_nome(valor)
    if texto.startswith("v"):
        return "V"
    if texto.startswith("i"):
        return "I"
    return texto[:1].upper()


def normalizar_cluster(valor: object) -> str:
    texto = normalizar_nome(valor)
    if not texto:
        return "Media Tecnologia"
    if "alta" in texto or "alto" in texto:
        return "Alta Tecnologia"
    if "baixa" in texto or "baixo" in texto:
        return "Baixa Tecnologia"
    if "media" in texto or "medio" in texto:
        return "Media Tecnologia"
    return str(valor).strip()


def fator_cluster_lote(lote: Lote) -> float:
    cluster = normalizar_nome(lote.cluster)
    if any(palavra in cluster for palavra in ["alta", "alto", "tech a", "tech-a", "nivel a", "a"]):
        return 1.05
    if any(palavra in cluster for palavra in ["baixa", "baixo", "tech b", "tech-b", "nivel b", "b"]):
        return 0.92
    return 1.0


def definir_status_base(peso_medio_g: float) -> str:
    if peso_medio_g >= PESO_DESPESCA_G:
        return "Peixe Pronto"
    return ""


def carregar_csv(caminho: Path) -> CsvTable:
    if not caminho.exists():
        raise FileNotFoundError(f"Arquivo nao encontrado: {caminho}")

    with caminho.open("r", encoding="utf-8-sig", newline="") as arquivo:
        reader = csv.DictReader(arquivo, delimiter=";")
        headers = list(reader.fieldnames or [])
        rows = [{k: (v or "") for k, v in row.items()} for row in reader]

    return CsvTable(headers=headers, rows=rows)


def normalizar_coluna_parametros(valor: object) -> str:
    return normalizar_nome(valor).replace(" ", "_")


def validar_colunas_parametros_gerenciais(df: pd.DataFrame) -> None:
    obrigatorias = set().union(*PARAMETROS_GERENCIAIS_REQUIRED_COLUMNS.values())
    ausentes = sorted(obrigatorias - set(df.columns))
    if ausentes:
        esperadas = ", ".join(sorted(obrigatorias))
        faltantes = ", ".join(ausentes)
        raise ValueError(
            "parametros_gerenciais.csv sem colunas obrigatorias. "
            f"Faltando: {faltantes}. Colunas esperadas: {esperadas}."
        )


def preparar_parametros_gerenciais(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    parametros = df.copy().fillna("")
    parametros.rename(columns={col: normalizar_coluna_parametros(col) for col in parametros.columns}, inplace=True)
    validar_colunas_parametros_gerenciais(parametros)

    tipo = parametros["tipo"].astype(str).map(normalizar_coluna_parametros)
    metas = parametros[tipo.isin(PARAMETROS_GERENCIAIS_TIPOS["metas"])].copy()
    abate = parametros[tipo.isin(PARAMETROS_GERENCIAIS_TIPOS["abate"])].copy()
    transferencias = parametros[tipo.isin(PARAMETROS_GERENCIAIS_TIPOS["transferencias"])].copy()

    if abate.empty:
        abate = metas.copy()

    return {
        "abate": abate[["tipo", "mes", "regiao", "dias_abate"]].reset_index(drop=True),
        "metas": metas[["tipo", "mes", "regiao", "po_diario_kg"]].reset_index(drop=True),
        "transferencias": transferencias[
            ["tipo", "mes", "regiao", "classe", "produtor", "volume_kg"]
        ].reset_index(drop=True),
    }


def ler_parametros_gerenciais(caminho: Path) -> dict[str, pd.DataFrame]:
    if not caminho.exists():
        raise FileNotFoundError(f"Arquivo nao encontrado: {caminho}")

    df = pd.read_csv(caminho, sep=";", encoding="utf-8-sig", dtype=str).fillna("")
    return preparar_parametros_gerenciais(df)


def preparar_curvas(tabela: CsvTable) -> list[Curva]:
    curvas_largas = preparar_curvas_largas(tabela)
    if curvas_largas:
        return curvas_largas

    col_dia = encontrar_coluna(
        tabela.headers, ALIASES_CURVAS["dia"], obrigatoria=False, contexto="curvas.csv"
    )
    col_regiao = encontrar_coluna(
        tabela.headers, ALIASES_CURVAS["regiao"], obrigatoria=False, contexto="curvas.csv"
    )
    col_estacao = encontrar_coluna(
        tabela.headers, ALIASES_CURVAS["estacao"], obrigatoria=False, contexto="curvas.csv"
    )
    col_cluster = encontrar_coluna(
        tabela.headers, ALIASES_CURVAS["cluster"], obrigatoria=False, contexto="curvas.csv"
    )
    col_peso = encontrar_coluna(
        tabela.headers, ALIASES_CURVAS["peso_ref"], obrigatoria=False, contexto="curvas.csv"
    )
    col_gdp = encontrar_coluna(
        tabela.headers, ALIASES_CURVAS["gdp"], obrigatoria=False, contexto="curvas.csv"
    )
    col_mort = encontrar_coluna(
        tabela.headers, ALIASES_CURVAS["mortalidade_pct"], obrigatoria=False, contexto="curvas.csv"
    )
    col_pv = encontrar_coluna(
        tabela.headers, ALIASES_CURVAS["pv_pct"], obrigatoria=False, contexto="curvas.csv"
    )
    col_marco = encontrar_coluna(
        tabela.headers, ALIASES_CURVAS["marco"], obrigatoria=False, contexto="curvas.csv"
    )
    col_racao = encontrar_coluna(
        tabela.headers, ALIASES_CURVAS["racao_und"], obrigatoria=False, contexto="curvas.csv"
    )

    # Se as colunas essenciais do formato estreito não existirem, retorna lista vazia
    # (o formato ainda não está implementado no curvas.csv atual)
    colunas_essenciais = [col_dia, col_estacao, col_peso, col_gdp, col_mort, col_pv, col_racao]
    if any(col is None for col in colunas_essenciais):
        return []

    curvas: list[Curva] = []
    for row in tabela.rows:
        dia = parse_numero_br(row[col_dia])
        peso = parse_numero_br(row[col_peso])
        gdp = parse_numero_br(row[col_gdp])
        mortalidade = parse_numero_br(row[col_mort])
        pv = parse_numero_br(row[col_pv])
        racao_und = parse_numero_br(row[col_racao])

        if any(math.isnan(v) for v in [dia, peso, gdp, mortalidade, pv, racao_und]):
            continue

        curvas.append(
            {
                "dia": int(round(dia)),
                "regiao": normalizar_nome(row[col_regiao]) if col_regiao else "",
                "estacao": normalizar_estacao(row[col_estacao]),
                "cluster": normalizar_cluster(row[col_cluster]) if col_cluster else "",
                "peso_ref_g": peso,
                "gdp_g": gdp,
                "mortalidade_pct": mortalidade,
                "pv": pv,
                "racao_und_g": racao_und,
                "marco": str(row[col_marco]).strip() if col_marco else "",
            }
        )

    if not curvas:
        raise ValueError("curvas.csv nao possui linhas validas apos a normalizacao.")

    return sorted(curvas, key=lambda c: (str(c["estacao"]), int(c["dia"])))


def preparar_curvas_largas(tabela: CsvTable) -> list[Curva]:
    configs = {
        "V": {
            "dia": ["dia verao"],
            "peso": ["pm verao", "peso medio verao", "peso verao"],
            "pv": ["pv verao"],
            "mort": ["mortalidade verao", "mortalidade pct verao"],
            "gdp": ["gdp verao"],
            "racao": ["qtd racao und verao", "racao und verao"],
            "marco": ["marco de gestao verao", "marco de gestao"],
        },
        "I": {
            "dia": ["dia inverno"],
            "peso": ["pm inverno", "peso medio inverno", "peso inverno"],
            "pv": ["pv inverno"],
            "mort": ["mortalidade inverno", "mortalidade pct inverno"],
            "gdp": ["gdp inverno"],
            "racao": ["qtd racao und inverno", "racao und inverno"],
            "marco": ["marco de gestao inverno", "marco de gestao c", "marco de gestao"],
        },
    }

    curvas: list[Curva] = []
    for estacao, aliases in configs.items():
        col_dia = encontrar_coluna(tabela.headers, aliases["dia"], obrigatoria=False)
        col_peso = encontrar_coluna(tabela.headers, aliases["peso"], obrigatoria=False)
        col_pv = encontrar_coluna(tabela.headers, aliases["pv"], obrigatoria=False)
        col_mort = encontrar_coluna(tabela.headers, aliases["mort"], obrigatoria=False)
        col_gdp = encontrar_coluna(tabela.headers, aliases["gdp"], obrigatoria=False)
        col_racao = encontrar_coluna(tabela.headers, aliases["racao"], obrigatoria=False)
        col_marco = encontrar_coluna(tabela.headers, aliases["marco"], obrigatoria=False)
        if not all([col_dia, col_peso, col_pv, col_mort, col_gdp, col_racao]):
            continue

        for row in tabela.rows:
            dia = parse_numero_br(row[col_dia])
            peso = parse_numero_br(row[col_peso])
            pv = parse_numero_br(row[col_pv])
            mortalidade = parse_numero_br(row[col_mort])
            gdp = parse_numero_br(row[col_gdp])
            racao_und = parse_numero_br(row[col_racao])
            if any(math.isnan(v) for v in [dia, peso, pv, mortalidade, gdp, racao_und]):
                continue
            curvas.append(
                {
                    "dia": int(round(dia)),
                    "estacao": estacao,
                    "cluster": "",
                    "peso_ref_g": peso,
                    "gdp_g": gdp,
                    "mortalidade_pct": mortalidade,
                    "pv": pv,
                    "racao_und_g": racao_und,
                    "marco": str(row[col_marco]).strip() if col_marco else "",
                }
            )

    return sorted(curvas, key=lambda c: (str(c["estacao"]), int(c["dia"])))


def preparar_tanques(tabela: CsvTable) -> dict[str, dict[str, str]]:
    col_tanque = encontrar_coluna(
        tabela.headers, ALIASES_TANQUES["tanque"], obrigatoria=False, contexto="tanques.csv"
    )
    if col_tanque is None:
        return {}

    col_regiao = encontrar_coluna(
        tabela.headers, ALIASES_TANQUES["regiao"], obrigatoria=False, contexto="tanques.csv"
    )
    col_classe = encontrar_coluna(
        tabela.headers, ALIASES_TANQUES["classe"], obrigatoria=False, contexto="tanques.csv"
    )

    tanques: dict[str, dict[str, str]] = {}
    for row in tabela.rows:
        tanque = str(row[col_tanque]).strip()
        if not tanque or tanque in tanques:
            continue
        tanques[tanque] = {
            "regiao": str(row[col_regiao]).strip() if col_regiao else "",
            "classe": str(row[col_classe]).strip() if col_classe else "",
        }
    return tanques


def preparar_racao(tabela: CsvTable) -> list[FaixaRacao]:
    col_peso_inicial = encontrar_coluna(
        tabela.headers, ALIASES_RACAO["peso_inicial"], contexto="racao.csv"
    )
    col_peso_final = encontrar_coluna(
        tabela.headers, ALIASES_RACAO["peso_final"], contexto="racao.csv"
    )
    col_preco = encontrar_coluna(tabela.headers, ALIASES_RACAO["preco_kg"], contexto="racao.csv")
    col_fase = encontrar_coluna(tabela.headers, ALIASES_RACAO["fase"], obrigatoria=False, contexto="racao.csv")

    faixas: list[FaixaRacao] = []
    for row in tabela.rows:
        peso_inicial = parse_numero_br(row[col_peso_inicial])
        peso_final = parse_numero_br(row[col_peso_final])
        preco = parse_numero_br(row[col_preco])
        fase = str(row[col_fase]).strip() if col_fase else ""
        if any(math.isnan(v) for v in [peso_inicial, peso_final, preco]):
            continue
        faixas.append(
            FaixaRacao(
                peso_inicial_g=peso_inicial,
                peso_final_g=peso_final,
                preco_kg=preco,
                fase=fase,
            )
        )

    if not faixas:
        raise ValueError("racao.csv nao possui faixas validas de peso/preco.")

    return sorted(faixas, key=lambda faixa: faixa.peso_inicial_g)


def buscar_faixa_racao(peso_medio_g: float, faixas_racao: list[FaixaRacao]) -> FaixaRacao | None:
    if not faixas_racao:
        return None
    
    if peso_medio_g <= faixas_racao[0].peso_inicial_g:
        return faixas_racao[0]
        
    for faixa in faixas_racao:
        if faixa.peso_inicial_g < peso_medio_g <= faixa.peso_final_g:
            return faixa
            
    return faixas_racao[-1]


def adicionar_custos_racao(
    registros: list[dict],
    faixas_racao: list[FaixaRacao],
    dia_solicitacao_relatorio: date,
) -> list[dict]:
    """Adiciona custo diario e acumulado de racao ao relatorio bruto, além de agrupar consumo por fase.

    O custo diario usa a faixa de preco em `racao.csv` correspondente ao peso
    medio da linha. O acumulado e zerado antes de `dia_solicitacao_relatorio`
    e, a partir dessa data, soma os custos diarios por lote.
    O consumo acumulado é recalculado para ser agrupado por fase nutricional.
    """
    consumo_acumulado_por_fase: dict[tuple[object, object, str], float] = {}
    resultado: list[dict] = []

    for registro in registros:
        linha = registro.copy()
        peso_medio = float(linha.get("Peso Medio (g)", 0.0) or 0.0)
        consumo_diario = float(linha.get("Consumo de Racao Diario (kg)", 0.0) or 0.0)
        q_peixes = float(linha.get("Quantidade de Peixes", 0.0) or 0.0)
        
        # Se não há peixes (ex: vazio sanitário), não há fase nutricional ativa
        if q_peixes > 0:
            faixa = buscar_faixa_racao(peso_medio, faixas_racao)
            preco_kg = faixa.preco_kg if faixa else 0.0
            fase = faixa.fase if faixa else ""
        else:
            faixa = None
            preco_kg = 0.0
            fase = ""
        
        custo_diario = consumo_diario * preco_kg

        lote_key = (linha.get("Produtor"), linha.get("Tanque"))
        fase_key = (*lote_key, fase)

        consumo_acumulado_por_fase[fase_key] = consumo_acumulado_por_fase.get(fase_key, 0.0) + consumo_diario

        linha["Custo de Racao Diario"] = custo_diario
        linha["Tipo de Ração"] = fase
        
        # Cria uma coluna específica para a Fase para não quebrar a matemática da TCA Acumulada
        linha["Consumo de Racao na Fase (kg)"] = consumo_acumulado_por_fase[fase_key]
        
        resultado.append(linha)

    if not resultado:
        return resultado

    df_resultado = pd.DataFrame(resultado)
    df_resultado = df_resultado.sort_values(["Produtor", "Tanque", "Data"], kind="mergesort")

    data_linha = pd.to_datetime(df_resultado["Data"])
    data_ref = pd.to_datetime(dia_solicitacao_relatorio)
    df_resultado["_custo_diario_para_acumulo"] = np.where(
        data_linha >= data_ref,
        df_resultado["Custo de Racao Diario"].fillna(0.0),
        0.0,
    )
    df_resultado["Custo de Racao Acumulado"] = (
        df_resultado.groupby(["Produtor", "Tanque"], sort=False)["_custo_diario_para_acumulo"]
        .cumsum()
    )
    df_resultado.drop(columns="_custo_diario_para_acumulo", inplace=True)

    return df_resultado.to_dict("records")


def colunas_plantel(tabela: CsvTable) -> dict[str, str | None]:
    return {
        chave: encontrar_coluna(
            tabela.headers,
            aliases,
            obrigatoria=chave not in {"produtor", "regiao", "classe", "cluster"},
            contexto="plantel.csv",
        )
        for chave, aliases in ALIASES_PLANTEL.items()
    }


def lote_da_linha(
    linha: dict[str, str], colunas: dict[str, str | None], tanques: dict[str, dict[str, str]]
) -> Lote:
    tanque_col = colunas["tanque"]
    quantidade_col = colunas["quantidade"]
    peso_col = colunas["peso_medio"]
    data_col = colunas["data_alojamento"]
    assert tanque_col and quantidade_col and peso_col and data_col

    tanque = str(linha[tanque_col]).strip()
    produtor = str(linha[colunas["produtor"]]).strip() if colunas.get("produtor") else ""
    regiao = str(linha[colunas["regiao"]]).strip() if colunas.get("regiao") else ""
    classe = str(linha[colunas["classe"]]).strip() if colunas.get("classe") else ""
    cluster = normalizar_cluster(linha[colunas["cluster"]]) if colunas.get("cluster") else "Media Tecnologia"

    cadastro = tanques.get(tanque, {})
    regiao = regiao or cadastro.get("regiao", "")
    classe = classe or cadastro.get("classe", "")

    quantidade = parse_numero_br(linha[quantidade_col])
    peso_medio_g = parse_numero_br(linha[peso_col])
    data_alojamento = parse_data_br(linha[data_col])

    if math.isnan(quantidade) or math.isnan(peso_medio_g):
        raise ValueError(f"quantidade ou peso medio invalido no tanque {tanque}")

    return Lote(
        produtor=produtor,
        tanque=tanque,
        regiao=regiao,
        classe=classe,
        cluster=cluster,
        quantidade=quantidade,
        peso_medio_g=peso_medio_g,
        data_alojamento=data_alojamento,
    )


def curvas_por_regiao_estacao_cluster(curvas: list[Curva], regiao: str, estacao: str, cluster: str = "") -> list[Curva]:
    regiao_norm = normalizar_nome(regiao)
    
    # 1. Filtra a região (se não achar a região específica, usa as curvas gerais como fallback)
    subset_regiao = [c for c in curvas if normalizar_nome(c.get("regiao", "")) == regiao_norm]
    if not subset_regiao:
        subset_regiao = curvas
        
    # 2. Filtra a estação
    subset_estacao = [c for c in subset_regiao if c["estacao"] == estacao] or subset_regiao
    
    # 3. Filtra o cluster
    cluster_normalizado = normalizar_cluster(cluster) if cluster else ""
    if cluster_normalizado:
        subset_cluster = [
            c for c in subset_estacao if normalizar_cluster(c.get("cluster", "")) == cluster_normalizado
        ]
        if subset_cluster:
            return subset_cluster
            
    return subset_estacao


def determinar_dia_ciclo(
    peso_medio_g: float,
    curvas: list[Curva],
    estacao_atual: str,
    cluster: str = "",
    regiao: str = "",
) -> int:
    subset = curvas_por_regiao_estacao_cluster(curvas, regiao, estacao_atual, cluster)
    curva = min(subset, key=lambda c: abs(float(c["peso_ref_g"]) - peso_medio_g))
    return int(curva["dia"])


def linha_curva(curvas: list[Curva], estacao: str, dia_ciclo: int, cluster: str = "", regiao: str = "") -> Curva:
    cache = getattr(linha_curva, "_cache", {})
    cluster_normalizado = normalizar_cluster(cluster) if cluster else ""
    regiao_norm = normalizar_nome(regiao)
    
    # O cache precisa considerar a região para não misturar APT com ITA
    cache_key = (id(curvas), regiao_norm, estacao, cluster_normalizado)
    
    if cache_key not in cache:
        subset = curvas_por_regiao_estacao_cluster(curvas, regiao, estacao, cluster_normalizado)
        subset = sorted(subset, key=lambda c: int(c["dia"]))
        cache[cache_key] = ([int(c["dia"]) for c in subset], subset)
        setattr(linha_curva, "_cache", cache)

    dias, subset = cache[cache_key]
    pos = bisect.bisect_right(dias, dia_ciclo) - 1
    if pos < 0:
        return subset[0]
    return subset[pos]


def normalizar_marcador_status(valor: object) -> str:
    texto = normalizar_nome(valor)
    if not texto:
        return ""
    if "pronto" in texto:
        return "Peixe Pronto"
    if "class 1" in texto or "classe 1" in texto:
        return "Class 1"
    if "class 2" in texto or "classe 2" in texto:
        return "Class 2"
    return ""


def definir_status(peso_medio_g: float, curva: Curva | None = None, dias_cultivo: int | None = None, data_atual: date | None = None, dt_ult_biometria: date | None = None) -> str:
    peso_medio_g = round(float(peso_medio_g), 2)
    
    # A primeira linha da projeção de cada tanque é sempre considerada a biometria inicial
    if dias_cultivo == 0:
        return "Biometria"
        
    if peso_medio_g >= PESO_DESPESCA_G:
        return "Peixe Pronto"
    if curva is None:
        return ""
    marcador = normalizar_marcador_status(curva.get("marco", ""))
    
    # Ignora os marcadores que são controlados de forma dinâmica pelo peso
    if marcador in ["Class 1", "Class 2", "Peixe Pronto"]:
        return ""
        
    if marcador:
        return marcador
    return ""


def curva_marca_peixe_pronto(curva: Curva) -> bool:
    return normalizar_marcador_status(curva.get("marco", "")) == "Peixe Pronto"


def peso_marcador_peixe_pronto(curvas: list[Curva], estacao: str, cluster: str = "", regiao: str = "") -> float:
    cache = getattr(peso_marcador_peixe_pronto, "_cache", {})
    cluster_normalizado = normalizar_cluster(cluster) if cluster else ""
    regiao_norm = normalizar_nome(regiao)
    cache_key = (id(curvas), regiao_norm, estacao, cluster_normalizado)
    
    if cache_key in cache:
        return cache[cache_key]

    candidatos = [
        float(curva["peso_ref_g"])
        for curva in curvas_por_regiao_estacao_cluster(curvas, regiao, estacao, cluster_normalizado)
        if curva_marca_peixe_pronto(curva)
    ]
    peso = min(candidatos) if candidatos else PESO_DESPESCA_G
    cache[cache_key] = peso
    setattr(peso_marcador_peixe_pronto, "_cache", cache)
    return peso


def atingiu_peixe_pronto(
    pm_real: float,
    curva: Curva,
    curvas: list[Curva],
    estacao: str,
    cluster: str = "",
    regiao: str = "",
) -> bool:
    return curva_marca_peixe_pronto(curva) or pm_real >= peso_marcador_peixe_pronto(
        curvas, estacao, cluster, regiao
    )


# def fator_regional_lote(lote: Lote) -> float:
#     regiao_norm = normalizar_nome(lote.regiao)
#     if "itapora" in regiao_norm or regiao_norm == "ita":
#         return 0.85
#     if "parana" in regiao_norm or regiao_norm == "prn":
#         return 0.85
#     return 1.0


def adicionar_registro(
    registros: list[dict[str, object]],
    lote: Lote,
    data_atual: date,
    semana: int,
    q_atual: float,
    pm_atual: float,
    bm_atual: float,
    cr_diario: float,
    cr_acumulado: float,
    tca_diario: float,
    tca_acumulado: float,
    gdp_diario: float,
    gdp_acumulado: float,
    mort_diaria_abs: float,
    mort_acumulada_abs: float,
    status: str,
    tanque_liberado: str | int = "",
    tanque_disponivel: str | int = "",
    ganho_bm_acumulado: float = 0.0,
) -> None:
    # Sobrevivencia %
    # Sobrevivencia Acumulada (%) = (Qtd Atual / Qtd Inicial) * 100
    sobrev_acumulada_pct = (q_atual / lote.quantidade) * 100.0 if lote.quantidade > 0 else 0.0
    # Sobrevivencia Diaria (%) = 100 - (Mortos Dia / Qtd Antes Mortos) * 100
    mort_taxa_dia = (mort_diaria_abs / (q_atual + mort_diaria_abs)) * 100.0 if (q_atual + mort_diaria_abs) > 0 else 0.0
    sobrev_diaria_pct = 100.0 - mort_taxa_dia
    
    registros.append(
        {
            "Produtor": lote.produtor,
            "Tanque": lote.tanque,
            "Data": data_atual,
            "Semana": semana,
            "Quantidade de Peixes": q_atual,
            "Peso Medio (g)": pm_atual,
            "Biomassa (kg)": bm_atual,
            "Consumo de Racao Diario (kg)": cr_diario,
            "Consumo de Racao Acumulado (kg)": cr_acumulado,
            "Ganho de Biomassa Acumulado (kg)": ganho_bm_acumulado,
            "TCA Diario": tca_diario,
            "TCA Acumulado": tca_acumulado,
            "GDP Diario (g/dia)": gdp_diario,
            "GDP Acumulado (g)": gdp_acumulado,
            "Mortalidade Diaria (peixes)": mort_diaria_abs,
            "Mortalidade Acumulada (peixes)": mort_acumulada_abs,
            "Sobrevivencia Diaria (%)": sobrev_diaria_pct,
            "Sobrevivencia Acumulada (%)": sobrev_acumulada_pct,
            "Status": status,
            "Regiao": lote.regiao,
            "Classe": lote.classe,
            "Tanques Liberados": tanque_liberado,
            "Tanques Disponivel": tanque_disponivel,
        }
    )


def simular_lote(
    lote: Lote,
    curvas: list[Curva],
    limite_dias: int = LIMITE_DIAS,
    data_relatorio: date | None = None,
) -> list[dict]:
    if lote.quantidade <= 0 or lote.peso_medio_g <= 0:
        return []

    data_relatorio = data_relatorio or date.today()
    data_inicial = lote.data_alojamento
    estacao_atual = detectar_estacao(data_inicial)
    
    # FATOR REGIONAL REMOVIDO: A punição matemática genérica saiu.
    # Agora apenas o fator tecnológico (cluster) é aplicado aqui.
    fator_desempenho = fator_cluster_lote(lote)

    q = lote.quantidade
    qi = lote.quantidade
    pi = lote.peso_medio_g
    pm_real = pi
    pm_relatorio = pi
    bm_inicial = qi * pi / 1000.0
    bm_anterior = bm_inicial

    ca_kg = 0.0
    mort_acumulada_abs = 0.0
    
    # Busca inicial de curvas já passando lote.regiao
    dc = determinar_dia_ciclo(pi, curvas, estacao_atual, lote.cluster, lote.regiao)
    curva_inicial = linha_curva(curvas, estacao_atual, dc, lote.cluster, lote.regiao)
    
    data_atual = data_inicial
    registros: list[dict[str, object]] = []
    peixe_pronto_no_historico = False
    data_liberacao: date | None = None
    class1_disparado = pi >= 30.0
    class2_disparado = pi >= 150.0

    adicionar_registro(
        registros,
        lote,
        data_inicial,
        1,
        q,
        pi,
        bm_inicial,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        definir_status(pi, curva_inicial, 0, data_inicial, lote.data_alojamento),
        "",
        "",
        0.0,
    )

    def simular_um_dia(data_dia: date, registrar: bool) -> None:
        nonlocal q, pm_real, pm_relatorio, bm_anterior, ca_kg
        nonlocal mort_acumulada_abs, dc, peixe_pronto_no_historico, estacao_atual, data_liberacao
        nonlocal class1_disparado, class2_disparado

        estacao = detectar_estacao(data_dia)
        if estacao != estacao_atual:
            # Passando lote.regiao na mudança de estação
            dc = determinar_dia_ciclo(pm_real, curvas, estacao, lote.cluster, lote.regiao)
            estacao_atual = estacao
            
        # Passando lote.regiao na busca da curva do dia
        curva = linha_curva(curvas, estacao, dc, lote.cluster, lote.regiao)
        
        pm_relatorio_anterior = pm_relatorio
        bm_anterior_dia = bm_anterior

        mortos_dia = q * (float(curva["mortalidade_pct"]) / 100.0)
        q = max(q - mortos_dia, 0.0)
        mort_acumulada_abs += mortos_dia

        pm_real += float(curva["gdp_g"]) * fator_desempenho

        ajuste_aplicado = False
        if registrar and data_dia == data_relatorio:
            dias_passados = (data_relatorio - data_inicial).days
            if dias_passados > 0:
                estacao_inicial = detectar_estacao(data_inicial)
                
                # Inserido lote.regiao nos ajustes
                dc_inicial = determinar_dia_ciclo(pi, curvas, estacao_inicial, lote.cluster, lote.regiao)
                dc_alvo = dc_inicial + dias_passados
                
                curva_alvo = linha_curva(curvas, estacao_inicial, dc_alvo, lote.cluster, lote.regiao)
                pm_real = float(curva_alvo["peso_ref_g"]) * FATOR_AJUSTE_PEIXE_PRONTO
                
                estacao_atual = detectar_estacao(data_relatorio)
                dc = determinar_dia_ciclo(pm_real, curvas, estacao_atual, lote.cluster, lote.regiao)
                
            ajuste_aplicado = True

        # Inserido lote.regiao na verificação do peixe pronto
        if atingiu_peixe_pronto(pm_real, curva, curvas, estacao, lote.cluster, lote.regiao):
            peixe_pronto_no_historico = True

        pm_relatorio = pm_real
        bm = q * pm_relatorio / 1000.0

        pv_rate = normalizar_taxa_pv(curva["pv"])
        racao_dia_kg = bm * pv_rate
        ca_kg += racao_dia_kg

        ganho_bm_dia = bm - bm_anterior_dia
        ganho_bm_total = bm - bm_inicial
        gdp_diario = 0.0 if ajuste_aplicado else pm_relatorio - pm_relatorio_anterior
        tca_diario = 0.0 if ajuste_aplicado or ganho_bm_dia <= 0 else racao_dia_kg / ganho_bm_dia
        tca_ac = ca_kg / ganho_bm_total if ganho_bm_total > 0 else 0.0

        # Verifica se os marcos foram atingidos neste exato dia
        trigger_class1_hoje = not class1_disparado and pm_relatorio >= 30.0
        trigger_class2_hoje = not class2_disparado and pm_relatorio >= 150.0
        trigger_peixe_pronto_hoje = data_liberacao is None and pm_relatorio >= PESO_DESPESCA_G

        # Atualiza as flags independentemente de registrar
        if trigger_class1_hoje:
            class1_disparado = True
        if trigger_class2_hoje:
            class2_disparado = True
        if trigger_peixe_pronto_hoje:
            data_liberacao = data_dia

        is_data_relatorio = data_dia == data_relatorio
        
        # Margens de tolerância apenas para o dia de geração do relatório
        exibir_class1 = trigger_class1_hoje or (is_data_relatorio and 28.0 <= pm_relatorio < 32.0)
        exibir_class2 = trigger_class2_hoje or (is_data_relatorio and 148.0 <= pm_relatorio < 152.0)
        exibir_peixe_pronto = trigger_peixe_pronto_hoje or (is_data_relatorio and PESO_DESPESCA_G - 2.0 <= pm_relatorio < PESO_DESPESCA_G + 2.0)

        if is_data_relatorio:
            if exibir_class1: class1_disparado = True
            if exibir_class2: class2_disparado = True
            if exibir_peixe_pronto and data_liberacao is None: data_liberacao = data_dia

        if registrar:
            dias_totais = (data_dia - data_inicial).days + 1
            dias_cultivo = max((data_dia - data_inicial).days, 1)
            semana_num = ((dias_totais - 1) // 7) + 1
            status = definir_status(pm_relatorio, curva, dias_cultivo, data_dia, lote.data_alojamento)
            
            ganho_peso_total = pm_relatorio - pi
            gdp_acumulado = ganho_peso_total / dias_cultivo
            
            tanque_liberado_val = ""
            tanque_disponivel_val = ""

            if exibir_peixe_pronto:
                status = "Peixe Pronto"
                tanque_liberado_val = (data_dia + timedelta(days=1)).strftime("%d/%m/%Y")
                tanque_disponivel_val = (data_dia + timedelta(days=1 + VAZIO_SANITARIO_DIAS)).strftime("%d/%m/%Y")
            elif exibir_class2:
                status = "Class 2"
                tanque_liberado_val = (data_dia + timedelta(days=1)).strftime("%d/%m/%Y")
                tanque_disponivel_val = (data_dia + timedelta(days=1 + VAZIO_SANITARIO_DIAS)).strftime("%d/%m/%Y")
            elif exibir_class1:
                status = "Class 1"
                tanque_liberado_val = (data_dia + timedelta(days=1)).strftime("%d/%m/%Y")
                tanque_disponivel_val = (data_dia + timedelta(days=1 + VAZIO_SANITARIO_DIAS)).strftime("%d/%m/%Y")

            adicionar_registro(
                registros,
                lote,
                data_dia,
                semana_num,
                q,
                pm_relatorio,
                bm,
                racao_dia_kg,
                ca_kg,
                tca_diario,
                tca_ac,
                gdp_diario,
                gdp_acumulado,
                mortos_dia,
                mort_acumulada_abs,
                status,
                tanque_liberado_val,
                tanque_disponivel_val,
                ganho_bm_total,
            )

        bm_anterior = bm
        dc += 1

        if ajuste_aplicado:
            pm_real = pm_relatorio
            peixe_pronto_no_historico = pm_relatorio >= PESO_DESPESCA_G

    while data_atual < data_relatorio and (data_atual - data_inicial).days < limite_dias:
        data_atual += timedelta(days=1)
        simular_um_dia(data_atual, registrar=data_atual == data_relatorio)
        if q <= 0:
            break

    if data_atual < data_relatorio or q <= 0:
        return registros

    while (
        pm_relatorio < PESO_DESPESCA_G
        and q > 0
        and (data_atual - data_inicial).days < limite_dias
    ):
        data_atual += timedelta(days=1)
        simular_um_dia(data_atual, registrar=True)

    return registros

def simular_todos_lotes(
    plantel: CsvTable,
    tanques: dict[str, dict[str, str]],
    curvas: list[Curva],
    *,
    mostrar_erros: bool = False,
    data_relatorio: date | None = None,
) -> list[dict]:
    colunas = colunas_plantel(plantel)
    resultados: list[dict] = []

    for idx, linha in enumerate(plantel.rows, start=2):
        try: # <--- O CINTO DE SEGURANÇA VOLTOU AQUI
            lote = lote_da_linha(linha, colunas, tanques)
            if lote.quantidade <= 0 or lote.peso_medio_g <= 0:
                continue
            resultados.extend(simular_lote(lote, curvas, data_relatorio=data_relatorio))
        except Exception as e:
            if mostrar_erros:
                print(f"Erro no tanque da linha {idx}: {e}")
            continue # Ignora o tanque com defeito e simula o próximo!

    return resultados    

def formatar_numero_saida(valor: object, casas: int) -> str:
    if valor is None:
        return ""
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return ""
    if math.isnan(numero):
        return ""
    texto = f"{numero:,.{casas}f}"
    return texto.replace(",", "_").replace(".", ",").replace("_", ".")


def formatar_inteiro_saida(valor: object) -> str:
    try:
        numero = int(round(float(valor or 0)))
    except (TypeError, ValueError):
        numero = 0
    return f"{numero:,}".replace(",", ".")


def formatar_relatorio(registros: list[dict]) -> list[dict[str, object]]:
    saida: list[dict[str, object]] = []
    casas_decimais = {
        "Peso Medio (g)": 2,
        "Biomassa (kg)": 2,
        "Consumo de Racao Diario (kg)": 2,
        "Consumo de Racao na Fase (kg)": 4,
        "Consumo de Racao Acumulado (kg)": 4,
        "Custo de Racao Diario": 2,
        "Custo de Racao Acumulado": 2,
        "Ganho de Biomassa Acumulado (kg)": 2,
        "TCA Diario": 4,
        "TCA Acumulado": 4,
        "GDP Diario (g/dia)": 4,
        "GDP Acumulado (g)": 4,
        "Sobrevivencia Diaria (%)": 2,
        "Sobrevivencia Acumulada (%)": 2,
    }
    colunas_inteiras = {
        "Semana",
        "Quantidade de Peixes",
        "Mortalidade Diaria (peixes)",
        "Mortalidade Acumulada (peixes)",
    }

    for registro in registros:
        linha = {}
        for coluna in SAIDA_COLUNAS:
            valor = registro.get(coluna, "")
            if coluna == "Data" and isinstance(valor, date):
                linha[coluna] = valor.strftime("%d/%m/%Y")
            elif coluna in casas_decimais:
                linha[coluna] = formatar_numero_saida(valor, casas_decimais[coluna])
            elif coluna in colunas_inteiras:
                linha[coluna] = formatar_inteiro_saida(valor)
            else:
                linha[coluna] = valor
        saida.append(linha)
    return saida


def salvar_csv(caminho: Path, registros: list[dict[str, object]]) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("w", encoding="utf-8-sig", newline="") as arquivo:
        writer = csv.DictWriter(arquivo, fieldnames=SAIDA_COLUNAS, delimiter=";")
        writer.writeheader()
        writer.writerows(registros)


def adicionar_timestamp_arquivo(caminho: Path, momento: datetime | None = None) -> Path:
    momento = momento or datetime.now()
    sufixo = momento.strftime("%Y%m%d_%H%M%S")
    return caminho.with_name(f"{caminho.stem}_{sufixo}{caminho.suffix}")


def salvar_plantel_nova_geracao(caminho: Path, registros: list[dict[str, object]]) -> None:
    """Exporta um plantel-base com tanques disponíveis para novo povoamento."""
    disponiveis: dict[str, dict[str, object]] = {}
    for registro in registros:
        if int(registro.get("Tanques Disponivel") or 0) != 1:
            continue
        tanque = str(registro.get("Tanque", "")).strip()
        if not tanque:
            continue
        data_registro = registro.get("Data")
        atual = disponiveis.get(tanque)
        if atual is None or data_registro < atual["Data Disponivel"]:
            disponiveis[tanque] = {
                "Produtor": "",
                "Tanque": tanque,
                "Data Entrada": data_registro,
                "Saldo Final": 0,
                "Dt.últ Biometria": data_registro,
                "Última Pesagem(g)": 0,
                "Região": registro.get("Regiao", ""),
                "Classe": registro.get("Classe", ""),
                "Status Planejamento": "Disponivel para novo povoamento",
                "Data Disponivel": data_registro,
            }

    fieldnames = [
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
    linhas = []
    for item in sorted(disponiveis.values(), key=lambda row: (row["Data Disponivel"], row["Tanque"])):
        linha = {campo: item.get(campo, "") for campo in fieldnames}
        for campo in ["Data Entrada", "Dt.últ Biometria"]:
            if isinstance(linha[campo], date):
                linha[campo] = linha[campo].strftime("%d/%m/%Y")
        linhas.append(linha)

    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("w", encoding="utf-8-sig", newline="") as arquivo:
        writer = csv.DictWriter(arquivo, fieldnames=fieldnames, delimiter=";")
        writer.writeheader()
        writer.writerows(linhas)


def executar(args: argparse.Namespace) -> Path:
    input_dir = resolve_runtime_path(args.input_dir)
    tanques = preparar_tanques(carregar_csv(resolve_input_file(input_dir, args.tanques)))
    plantel = carregar_csv(resolve_input_file(input_dir, args.plantel))
    curvas = preparar_curvas(carregar_csv(resolve_input_file(input_dir, args.curvas)))
    if not curvas:
        raise ValueError(
            "curvas.csv nao possui colunas reconhecidas. "
            "Verifique se o arquivo esta no formato correto (largo ou estreito)."
        )
    racao = preparar_racao(carregar_csv(resolve_input_file(input_dir, args.racao)))
    parametros_gerenciais = getattr(args, "parametros_gerenciais", "parametros_gerenciais.csv")
    ler_parametros_gerenciais(resolve_input_file(input_dir, parametros_gerenciais))
    data_relatorio = parse_data_br(args.data_relatorio) if args.data_relatorio else date.today()
    momento_geracao = datetime.now()

    resultado = simular_todos_lotes(
        plantel=plantel,
        tanques=tanques,
        curvas=curvas,
        mostrar_erros=args.mostrar_erros,
        data_relatorio=data_relatorio,
    )
    resultado = adicionar_custos_racao(resultado, racao, data_relatorio)
    plantel_nova_geracao = getattr(args, "plantel_nova_geracao_output", "")
    if plantel_nova_geracao:
        plantel_output = Path(plantel_nova_geracao)
        if not plantel_output.is_absolute():
            plantel_output = resolve_runtime_path(plantel_output)
        plantel_output = adicionar_timestamp_arquivo(plantel_output, momento_geracao)
        salvar_plantel_nova_geracao(plantel_output, resultado)
    resultado_br = formatar_relatorio(resultado)

    output = Path(args.output)
    if not output.is_absolute():
        output = resolve_runtime_path(output)
    output = adicionar_timestamp_arquivo(output, momento_geracao)
    salvar_csv(output, resultado_br)
    return output


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Simulador de Planejamento Aquicola Mar&Terra."
    )
    parser.add_argument("--input-dir", default=r".\data\input", help="Pasta onde estao os CSVs de entrada.")
    parser.add_argument("--tanques", default="tanques.csv", help="Nome do arquivo tanques.csv.")
    parser.add_argument("--plantel", default="plantel.csv", help="Nome do arquivo plantel.csv.")
    parser.add_argument("--curvas", default="curvas.csv", help="Nome do arquivo curvas.csv.")
    parser.add_argument("--racao", default="racao.csv", help="Nome do arquivo racao.csv.")
    parser.add_argument(
        "--parametros-gerenciais",
        default="parametros_gerenciais.csv",
        help="Nome do arquivo parametros_gerenciais.csv.",
    )
    parser.add_argument(
        "--output",
        default=r".\data\output\simulacao_completa_br.csv",
        help="Arquivo CSV de saida.",
    )
    parser.add_argument(
        "--mostrar-erros",
        action="store_true",
        help="Mostra lotes ignorados por inconsistencias de dados.",
    )
    parser.add_argument(
        "--data-relatorio",
        default="",
        help="Data de geracao do relatorio no formato dd/mm/aaaa ou aaaa-mm-dd. Padrao: hoje.",
    )
    parser.add_argument(
        "--plantel-nova-geracao-output",
        default="",
        help="CSV opcional com tanques disponiveis para planejamento de novo povoamento.",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    output = executar(args)
    print(f"Simulacao concluida: {output}")


if __name__ == "__main__":
    main()
