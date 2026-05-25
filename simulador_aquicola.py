from __future__ import annotations

import argparse
import csv
import math
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable


PESO_DESPESCA_G = 900.0
LIMITE_DIAS = 730


SAIDA_COLUNAS = [
    "Produtor",
    "Tanque",
    "Data",
    "Semana",
    "Quantidade de Peixes",
    "Peso Medio (g)",
    "Biomassa (kg)",
    "Consumo de Racao na Semana (kg)",
    "Consumo de Racao Acumulado (kg)",
    "TCA da Semana",
    "TCA Acumulado",
    "GDP Medio da Semana (g/dia)",
    "GDP Medio Acumulado (g/dia)",
    "Mortalidade da Semana (%)",
    "Mortalidade Acumulada (%)",
    "Sobrevivencia da Semana (%)",
    "Sobrevivencia Acumulada (%)",
    "Status",
    "Regiao",
    "Classe",
    "Tanques Liberados",
    "Tanques Disponivel",
]


ALIASES_PLANTEL = {
    "produtor": ["produtor", "proprietario", "cliente", "fazenda"],
    "tanque": ["tanque", "id tanque", "tanque id", "estrutura", "viveiro"],
    "regiao": ["regiao", "regiao produtor", "localidade", "area"],
    "classe": ["classe", "classificacao", "tipo", "categoria"],
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
    "estacao": ["estacao", "sazonalidade", "periodo", "epoca"],
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
}


ALIASES_TANQUES = {
    "tanque": ["tanque", "id tanque", "tanque id", "estrutura", "viveiro"],
    "regiao": ["regiao", "regiao produtor", "localidade", "area"],
    "classe": ["classe", "classificacao", "tipo", "categoria"],
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
    quantidade: float
    peso_medio_g: float
    data_alojamento: date


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

    percentual = "%" in texto
    texto = texto.replace("%", "").replace(" ", "")
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    else:
        texto = texto.replace(",", ".")

    try:
        numero = float(texto)
    except ValueError:
        return math.nan
    return numero / 100.0 if percentual else numero


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
    return "V" if data_ref.month in {10, 11, 12, 1, 2, 3} else "I"


def normalizar_estacao(valor: object) -> str:
    texto = normalizar_nome(valor)
    if texto.startswith("v"):
        return "V"
    if texto.startswith("i"):
        return "I"
    return texto[:1].upper()


def definir_status(peso_medio_g: float) -> str:
    if peso_medio_g < 30:
        return "Alevinagem"
    if peso_medio_g < 120:
        return "Class 1 \u2014 Recria"
    if peso_medio_g < PESO_DESPESCA_G:
        return "Class 2 \u2014 Engorda"
    return "Despescado"


def carregar_csv(caminho: Path) -> CsvTable:
    if not caminho.exists():
        raise FileNotFoundError(f"Arquivo nao encontrado: {caminho}")

    with caminho.open("r", encoding="utf-8-sig", newline="") as arquivo:
        reader = csv.DictReader(arquivo, delimiter=";")
        headers = list(reader.fieldnames or [])
        rows = [{k: (v or "") for k, v in row.items()} for row in reader]

    return CsvTable(headers=headers, rows=rows)


def preparar_curvas(tabela: CsvTable) -> list[Curva]:
    curvas_largas = preparar_curvas_largas(tabela)
    if curvas_largas:
        return curvas_largas

    col_dia = encontrar_coluna(tabela.headers, ALIASES_CURVAS["dia"], contexto="curvas.csv")
    col_estacao = encontrar_coluna(
        tabela.headers, ALIASES_CURVAS["estacao"], contexto="curvas.csv"
    )
    col_peso = encontrar_coluna(tabela.headers, ALIASES_CURVAS["peso_ref"], contexto="curvas.csv")
    col_gdp = encontrar_coluna(tabela.headers, ALIASES_CURVAS["gdp"], contexto="curvas.csv")
    col_mort = encontrar_coluna(
        tabela.headers, ALIASES_CURVAS["mortalidade_pct"], contexto="curvas.csv"
    )
    col_pv = encontrar_coluna(tabela.headers, ALIASES_CURVAS["pv_pct"], contexto="curvas.csv")

    curvas: list[Curva] = []
    for row in tabela.rows:
        dia = parse_numero_br(row[col_dia])
        peso = parse_numero_br(row[col_peso])
        gdp = parse_numero_br(row[col_gdp])
        mortalidade = parse_numero_br(row[col_mort])
        pv = parse_numero_br(row[col_pv])

        if any(math.isnan(v) for v in [dia, peso, gdp, mortalidade, pv]):
            continue

        curvas.append(
            {
                "dia": int(round(dia)),
                "estacao": normalizar_estacao(row[col_estacao]),
                "peso_ref_g": peso,
                "gdp_g": gdp,
                "mortalidade_pct": mortalidade,
                "pv": pv,
            }
        )

    if not curvas:
        raise ValueError("curvas.csv nao possui linhas validas apos a normalizacao.")

    # PV pode vir como fracao (0,025) ou percentual (2,5). Normaliza para fracao.
    if max(float(c["pv"]) for c in curvas) > 1:
        for curva in curvas:
            curva["pv"] = float(curva["pv"]) / 100.0

    return sorted(curvas, key=lambda c: (str(c["estacao"]), int(c["dia"])))


def preparar_curvas_largas(tabela: CsvTable) -> list[Curva]:
    configs = {
        "V": {
            "dia": ["dia verao"],
            "peso": ["pm verao", "peso medio verao", "peso verao"],
            "pv": ["pv verao"],
            "mort": ["mortalidade verao", "mortalidade pct verao"],
            "gdp": ["gdp verao"],
        },
        "I": {
            "dia": ["dia inverno"],
            "peso": ["pm inverno", "peso medio inverno", "peso inverno"],
            "pv": ["pv inverno"],
            "mort": ["mortalidade inverno", "mortalidade pct inverno"],
            "gdp": ["gdp inverno"],
        },
    }

    curvas: list[Curva] = []
    for estacao, aliases in configs.items():
        col_dia = encontrar_coluna(tabela.headers, aliases["dia"], obrigatoria=False)
        col_peso = encontrar_coluna(tabela.headers, aliases["peso"], obrigatoria=False)
        col_pv = encontrar_coluna(tabela.headers, aliases["pv"], obrigatoria=False)
        col_mort = encontrar_coluna(tabela.headers, aliases["mort"], obrigatoria=False)
        col_gdp = encontrar_coluna(tabela.headers, aliases["gdp"], obrigatoria=False)
        if not all([col_dia, col_peso, col_pv, col_mort, col_gdp]):
            continue

        for row in tabela.rows:
            dia = parse_numero_br(row[col_dia])
            peso = parse_numero_br(row[col_peso])
            pv = parse_numero_br(row[col_pv])
            mortalidade = parse_numero_br(row[col_mort])
            gdp = parse_numero_br(row[col_gdp])
            if any(math.isnan(v) for v in [dia, peso, pv, mortalidade, gdp]):
                continue
            curvas.append(
                {
                    "dia": int(round(dia)),
                    "estacao": estacao,
                    "peso_ref_g": peso,
                    "gdp_g": gdp,
                    "mortalidade_pct": mortalidade,
                    "pv": pv,
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


def colunas_plantel(tabela: CsvTable) -> dict[str, str | None]:
    return {
        chave: encontrar_coluna(
            tabela.headers,
            aliases,
            obrigatoria=chave not in {"produtor", "regiao", "classe"},
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
        quantidade=quantidade,
        peso_medio_g=peso_medio_g,
        data_alojamento=data_alojamento,
    )


def determinar_dia_ciclo(peso_medio_g: float, curvas: list[Curva], estacao: str) -> int:
    subset = [c for c in curvas if c["estacao"] == estacao] or curvas
    curva = min(subset, key=lambda c: abs(float(c["peso_ref_g"]) - peso_medio_g))
    return int(curva["dia"])


def linha_curva(curvas: list[Curva], estacao: str, dia_ciclo: int) -> Curva:
    subset = [c for c in curvas if c["estacao"] == estacao] or curvas
    anteriores = [c for c in subset if int(c["dia"]) <= dia_ciclo]
    if anteriores:
        return max(anteriores, key=lambda c: int(c["dia"]))
    return min(subset, key=lambda c: int(c["dia"]))


def adicionar_registro(
    registros: list[dict[str, object]],
    lote: Lote,
    data_atual: date,
    semana: int,
    q_atual: float,
    pm_atual: float,
    bm_atual: float,
    cr_semana: float,
    cr_acumulado: float,
    tca_semana: float,
    tca_acumulado: float,
    gdp_semana: float,
    gdp_acumulado: float,
    mortalidade_semana_pct: float,
    mortos_acumulado: float,
) -> None:
    mortalidade_acumulada_pct = (
        mortos_acumulado / lote.quantidade * 100.0 if lote.quantidade > 0 else 0.0
    )
    registros.append(
        {
            "Produtor": lote.produtor,
            "Tanque": lote.tanque,
            "Data": data_atual,
            "Semana": semana,
            "Quantidade de Peixes": q_atual,
            "Peso Medio (g)": pm_atual,
            "Biomassa (kg)": bm_atual,
            "Consumo de Racao na Semana (kg)": cr_semana,
            "Consumo de Racao Acumulado (kg)": cr_acumulado,
            "TCA da Semana": tca_semana,
            "TCA Acumulado": tca_acumulado,
            "GDP Medio da Semana (g/dia)": gdp_semana,
            "GDP Medio Acumulado (g/dia)": gdp_acumulado,
            "Mortalidade da Semana (%)": mortalidade_semana_pct,
            "Mortalidade Acumulada (%)": mortalidade_acumulada_pct,
            "Sobrevivencia da Semana (%)": max(100.0 - mortalidade_semana_pct, 0.0),
            "Sobrevivencia Acumulada (%)": max(100.0 - mortalidade_acumulada_pct, 0.0),
            "Status": definir_status(pm_atual),
            "Regiao": lote.regiao,
            "Classe": lote.classe,
            "Tanques Liberados": "",
            "Tanques Disponivel": "",
        }
    )


def simular_lote(lote: Lote, curvas: list[Curva], limite_dias: int = LIMITE_DIAS) -> list[dict]:
    if lote.quantidade <= 0 or not (0 < lote.peso_medio_g < PESO_DESPESCA_G):
        return []

    estacao_inicial = detectar_estacao(lote.data_alojamento)
    dia_ciclo = determinar_dia_ciclo(lote.peso_medio_g, curvas, estacao_inicial)

    q_atual = lote.quantidade
    pm_atual = lote.peso_medio_g
    bm_inicial = q_atual * pm_atual / 1000.0
    data_inicial = lote.data_alojamento

    cr_acumulado = 0.0
    mortos_acumulado = 0.0
    gdp_total = 0.0
    dias_total = 0

    cr_semana = 0.0
    gdp_total_semana = 0.0
    dias_semana = 0
    bm_inicio_semana = bm_inicial
    q_inicio_semana = q_atual
    mortos_semana = 0.0

    registros: list[dict[str, object]] = []

    for dia_simulado in range(1, limite_dias + 1):
        data_atual = data_inicial + timedelta(days=dia_simulado - 1)
        semana = dia_simulado // 7 + 1
        estacao = detectar_estacao(data_atual)
        curva = linha_curva(curvas, estacao, dia_ciclo)

        mortos_dia = q_atual * (float(curva["mortalidade_pct"]) / 100.0)
        q_atual = max(q_atual - mortos_dia, 0.0)
        gdp_dia = float(curva["gdp_g"])
        pm_atual = pm_atual + gdp_dia
        bm_atual = q_atual * pm_atual / 1000.0
        cr_dia = bm_atual * float(curva["pv"])

        cr_semana += cr_dia
        cr_acumulado += cr_dia
        mortos_acumulado += mortos_dia
        mortos_semana += mortos_dia
        gdp_total += gdp_dia
        gdp_total_semana += gdp_dia
        dias_total += 1
        dias_semana += 1

        delta_bm_semana = bm_atual - bm_inicio_semana
        delta_bm_total = bm_atual - bm_inicial
        fechamento_semana = dia_simulado % 7 == 0
        tca_semana = (
            cr_semana / delta_bm_semana if fechamento_semana and delta_bm_semana > 0 else 0.0
        )
        tca_acumulado = cr_acumulado / delta_bm_total if delta_bm_total > 0 else 0.0
        gdp_semana = gdp_total_semana / dias_semana if fechamento_semana and dias_semana else 0.0
        gdp_acumulado = gdp_total / dias_total if dias_total else 0.0
        mortalidade_semana_pct = (
            mortos_semana / q_inicio_semana * 100.0 if q_inicio_semana > 0 else 0.0
        )

        adicionar_registro(
            registros,
            lote,
            data_atual,
            semana,
            q_atual,
            pm_atual,
            bm_atual,
            0.0 if fechamento_semana else cr_semana,
            cr_acumulado,
            tca_semana,
            tca_acumulado,
            gdp_semana,
            gdp_acumulado,
            mortalidade_semana_pct,
            mortos_acumulado,
        )

        if fechamento_semana:
            cr_semana = 0.0
            gdp_total_semana = 0.0
            dias_semana = 0
            bm_inicio_semana = bm_atual
            q_inicio_semana = q_atual
            mortos_semana = 0.0

        dia_ciclo += 1

        if pm_atual >= PESO_DESPESCA_G or q_atual <= 0:
            break

    return registros


def simular_todos_lotes(
    plantel: CsvTable,
    tanques: dict[str, dict[str, str]],
    curvas: list[Curva],
    *,
    mostrar_erros: bool = False,
) -> list[dict]:
    colunas = colunas_plantel(plantel)
    resultados: list[dict] = []

    for idx, linha in enumerate(plantel.rows, start=2):
        try:
            lote = lote_da_linha(linha, colunas, tanques)
            if lote.quantidade <= 0 or not (0 < lote.peso_medio_g < PESO_DESPESCA_G):
                continue
            resultados.extend(simular_lote(lote, curvas))
        except Exception as exc:
            if mostrar_erros:
                print(f"Lote ignorado na linha {idx}: {exc}")
            continue

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
    texto = f"{numero:.{casas}f}".rstrip("0").rstrip(".")
    return texto if "." in texto else f"{texto}.0"


def formatar_relatorio(registros: list[dict]) -> list[dict[str, object]]:
    saida: list[dict[str, object]] = []
    casas_decimais = {
        "Peso Medio (g)": 2,
        "Biomassa (kg)": 2,
        "Consumo de Racao na Semana (kg)": 2,
        "Consumo de Racao Acumulado (kg)": 4,
        "TCA da Semana": 4,
        "TCA Acumulado": 4,
        "GDP Medio da Semana (g/dia)": 4,
        "GDP Medio Acumulado (g/dia)": 4,
        "Mortalidade da Semana (%)": 2,
        "Mortalidade Acumulada (%)": 2,
        "Sobrevivencia da Semana (%)": 2,
        "Sobrevivencia Acumulada (%)": 2,
    }

    for registro in registros:
        linha = {}
        for coluna in SAIDA_COLUNAS:
            valor = registro.get(coluna, "")
            if coluna == "Data" and isinstance(valor, date):
                linha[coluna] = valor.strftime("%Y-%m-%d")
            elif coluna in casas_decimais:
                linha[coluna] = formatar_numero_saida(valor, casas_decimais[coluna])
            elif coluna == "Quantidade de Peixes":
                linha[coluna] = int(round(float(valor or 0)))
            else:
                linha[coluna] = valor
        saida.append(linha)
    return saida


def salvar_csv(caminho: Path, registros: list[dict[str, object]]) -> None:
    with caminho.open("w", encoding="utf-8-sig", newline="") as arquivo:
        writer = csv.DictWriter(arquivo, fieldnames=SAIDA_COLUNAS, delimiter=",")
        writer.writeheader()
        writer.writerows(registros)


def executar(args: argparse.Namespace) -> Path:
    input_dir = Path(args.input_dir)
    tanques = preparar_tanques(carregar_csv(input_dir / args.tanques))
    plantel = carregar_csv(input_dir / args.plantel)
    curvas = preparar_curvas(carregar_csv(input_dir / args.curvas))

    # racao.csv e carregado para validar a presenca da matriz descrita.
    carregar_csv(input_dir / args.racao)

    resultado = simular_todos_lotes(
        plantel=plantel,
        tanques=tanques,
        curvas=curvas,
        mostrar_erros=args.mostrar_erros,
    )
    resultado_br = formatar_relatorio(resultado)

    output = Path(args.output)
    if not output.is_absolute():
        output = input_dir / output
    salvar_csv(output, resultado_br)
    return output


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Simulador de Planejamento Aquicola Mar&Terra."
    )
    parser.add_argument("--input-dir", default=".", help="Pasta onde estao os CSVs de entrada.")
    parser.add_argument("--tanques", default="tanques.csv", help="Nome do arquivo tanques.csv.")
    parser.add_argument("--plantel", default="plantel.csv", help="Nome do arquivo plantel.csv.")
    parser.add_argument("--curvas", default="curvas.csv", help="Nome do arquivo curvas.csv.")
    parser.add_argument("--racao", default="racao.csv", help="Nome do arquivo racao.csv.")
    parser.add_argument(
        "--output",
        default="simulacao_completa_br.csv",
        help="Arquivo CSV de saida.",
    )
    parser.add_argument(
        "--mostrar-erros",
        action="store_true",
        help="Mostra lotes ignorados por inconsistencias de dados.",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    output = executar(args)
    print(f"Simulacao concluida: {output}")


if __name__ == "__main__":
    main()
