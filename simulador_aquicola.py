from __future__ import annotations

import argparse
import bisect
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
FATOR_AJUSTE_PEIXE_PRONTO = 0.84
MARCADOR_PEIXE_PRONTO = "pronto"


SAIDA_COLUNAS = [
    "Produtor",
    "Tanque",
    "Data",
    "Semana",
    "Quantidade de Peixes",
    "Peso Medio (g)",
    "Biomassa (kg)",
    "Consumo de Racao Diario (kg)",
    "Consumo de Racao Acumulado (kg)",
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

    texto = texto.replace("%", "").replace(" ", "")
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    else:
        texto = texto.replace(",", ".")

    try:
        return float(texto)
    except ValueError:
        return math.nan


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
    col_marco = encontrar_coluna(
        tabela.headers, ALIASES_CURVAS["marco"], obrigatoria=False, contexto="curvas.csv"
    )
    col_racao = encontrar_coluna(tabela.headers, ALIASES_CURVAS["racao_und"], contexto="curvas.csv")

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
                "estacao": normalizar_estacao(row[col_estacao]),
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


def determinar_dia_ciclo(peso_medio_g: float, curvas: list[Curva], estacao_atual: str) -> int:
    # A logica do notebook busca o peso mais proximo em AMBAS as estacoes para definir o dia inicial
    curva = min(curvas, key=lambda c: abs(float(c["peso_ref_g"]) - peso_medio_g))
    return int(curva["dia"])


def linha_curva(curvas: list[Curva], estacao: str, dia_ciclo: int) -> Curva:
    cache = getattr(linha_curva, "_cache", {})
    cache_key = (id(curvas), estacao)
    if cache_key not in cache:
        subset = [c for c in curvas if c["estacao"] == estacao] or curvas
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


def definir_status(peso_medio_g: float, curva: Curva | None = None) -> str:
    peso_medio_g = round(float(peso_medio_g), 2)
    if peso_medio_g >= PESO_DESPESCA_G:
        return "Peixe Pronto"
    if peso_medio_g == 120.0:
        return "Class 2"
    if peso_medio_g == 30.0:
        return "Class 1"
    if curva is None:
        return ""
    return normalizar_marcador_status(curva.get("marco", ""))


def curva_marca_peixe_pronto(curva: Curva) -> bool:
    return normalizar_marcador_status(curva.get("marco", "")) == "Peixe Pronto"


def peso_marcador_peixe_pronto(curvas: list[Curva], estacao: str) -> float:
    cache = getattr(peso_marcador_peixe_pronto, "_cache", {})
    cache_key = (id(curvas), estacao)
    if cache_key in cache:
        return cache[cache_key]

    candidatos = [
        float(curva["peso_ref_g"])
        for curva in curvas
        if curva["estacao"] == estacao and curva_marca_peixe_pronto(curva)
    ]
    peso = min(candidatos) if candidatos else PESO_DESPESCA_G
    cache[cache_key] = peso
    setattr(peso_marcador_peixe_pronto, "_cache", cache)
    return peso


def atingiu_peixe_pronto(pm_real: float, curva: Curva, curvas: list[Curva], estacao: str) -> bool:
    return curva_marca_peixe_pronto(curva) or pm_real >= peso_marcador_peixe_pronto(curvas, estacao)


def fator_regional_lote(lote: Lote) -> float:
    regiao_norm = normalizar_nome(lote.regiao)
    if "itapora" in regiao_norm:
        return 0.80
    if "parana" in regiao_norm:
        return 0.85
    return 1.0


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
            "Tanques Liberados": "",
            "Tanques Disponivel": "",
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
    fator_regional = fator_regional_lote(lote)

    q = lote.quantidade
    qi = lote.quantidade
    pi = lote.peso_medio_g
    pm_real = pi
    pm_relatorio = pi
    bm_inicial = qi * pi / 1000.0
    bm_anterior = bm_inicial

    ca_kg = 0.0
    mort_acumulada_abs = 0.0
    dc = determinar_dia_ciclo(pi, curvas, detectar_estacao(data_inicial))
    curva_inicial = linha_curva(curvas, detectar_estacao(data_inicial), dc)
    data_atual = data_inicial
    registros: list[dict[str, object]] = []
    peixe_pronto_no_historico = False

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
        definir_status(pi, curva_inicial),
    )

    def simular_um_dia(data_dia: date, registrar: bool) -> None:
        nonlocal q, pm_real, pm_relatorio, bm_anterior, ca_kg
        nonlocal mort_acumulada_abs, dc, peixe_pronto_no_historico

        estacao = detectar_estacao(data_dia)
        curva = linha_curva(curvas, estacao, dc)
        pm_relatorio_anterior = pm_relatorio
        bm_anterior_dia = bm_anterior

        mortos_dia = q * (float(curva["mortalidade_pct"]) / 100.0)
        q = max(q - mortos_dia, 0.0)
        mort_acumulada_abs += mortos_dia

        pm_real += float(curva["gdp_g"]) * fator_regional
        if atingiu_peixe_pronto(pm_real, curva, curvas, estacao):
            peixe_pronto_no_historico = True

        ajuste_aplicado = registrar and data_dia == data_relatorio and peixe_pronto_no_historico
        pm_relatorio = pm_real * FATOR_AJUSTE_PEIXE_PRONTO if ajuste_aplicado else pm_real
        bm = q * pm_relatorio / 1000.0

        pv_rate = (float(curva["pv"]) / 100.0) * fator_regional
        racao_dia_kg = bm * pv_rate
        ca_kg += racao_dia_kg

        ganho_bm_dia = bm - bm_anterior_dia
        ganho_bm_total = bm - bm_inicial
        gdp_diario = 0.0 if ajuste_aplicado else pm_relatorio - pm_relatorio_anterior
        tca_diario = 0.0 if ajuste_aplicado or ganho_bm_dia <= 0 else racao_dia_kg / ganho_bm_dia
        tca_ac = ca_kg / ganho_bm_total if ganho_bm_total > 0 else 0.0

        if registrar:
            dias_totais = (data_dia - data_inicial).days + 1
            semana_num = ((dias_totais - 1) // 7) + 1
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
                pm_relatorio - pi,
                mortos_dia,
                mort_acumulada_abs,
                definir_status(pm_relatorio, curva),
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
        try:
            lote = lote_da_linha(linha, colunas, tanques)
            if lote.quantidade <= 0 or lote.peso_medio_g <= 0:
                continue
            resultados.extend(simular_lote(lote, curvas, data_relatorio=data_relatorio))
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
        "Consumo de Racao Acumulado (kg)": 4,
        "TCA Diario": 4,
        "TCA Acumulado": 4,
        "GDP Diario (g/dia)": 4,
        "GDP Acumulado (g)": 4,
        "Mortalidade Diaria (peixes)": 2,
        "Mortalidade Acumulada (peixes)": 2,
        "Sobrevivencia Diaria (%)": 2,
        "Sobrevivencia Acumulada (%)": 2,
    }
    colunas_inteiras = {"Semana", "Quantidade de Peixes"}

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
    with caminho.open("w", encoding="utf-8-sig", newline="") as arquivo:
        writer = csv.DictWriter(arquivo, fieldnames=SAIDA_COLUNAS, delimiter=";")
        writer.writeheader()
        writer.writerows(registros)


def executar(args: argparse.Namespace) -> Path:
    input_dir = Path(args.input_dir)
    tanques = preparar_tanques(carregar_csv(input_dir / args.tanques))
    plantel = carregar_csv(input_dir / args.plantel)
    curvas = preparar_curvas(carregar_csv(input_dir / args.curvas))
    data_relatorio = parse_data_br(args.data_relatorio) if args.data_relatorio else date.today()

    # racao.csv e carregado para validar a presenca da matriz descrita.
    carregar_csv(input_dir / args.racao)

    resultado = simular_todos_lotes(
        plantel=plantel,
        tanques=tanques,
        curvas=curvas,
        mostrar_erros=args.mostrar_erros,
        data_relatorio=data_relatorio,
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
    parser.add_argument(
        "--data-relatorio",
        default="",
        help="Data de geracao do relatorio no formato dd/mm/aaaa ou aaaa-mm-dd. Padrao: hoje.",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    output = executar(args)
    print(f"Simulacao concluida: {output}")


if __name__ == "__main__":
    main()
