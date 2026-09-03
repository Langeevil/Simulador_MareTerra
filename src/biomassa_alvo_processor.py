"""
biomassa_alvo_processor.py — Planejamento de despesca (Mar & Terra)

Módulo consolidado da camada de despesca do simulador aquícola.

Fluxo do pipeline:
  1. processar_biomassa_alvo()      -> seleciona tanques elegíveis e gera a "foto" de maior peso médio.
  2. alocar_biomassa()              -> Fase 1 (produção própria) + Fase 2 (saldo entre produtores), com carry-over da fração remanescente do tanque entre meses.
  3. compor_cargas_parciais()       -> empacota alocações em cargas de 7.000 a 10.000 kg com despesca parcial.
  4. distribuir_semanas_parciais()  -> distribui cargas nas semanas do mês (quota semanal, sem repetir tanque na mesma semana).
  5. aplicar_despesca_parcial_no_relatorio() -> aplica a linha do tempo de despesca (Status ordinal, Tanques Liberados/Disponivel, corte seco, peso congelado).
  6. gerar_relatorio_sobras_faltas() -> relatório de fechamento (Alvo x Disponível x Alocado x Recebido x Sobra x Falta).

REGRAS DE STATUS:
  - Despesca em UMA única carga que esvazia o tanque -> "Despesca Única" (preenche colunas de tanques).
  - Despesca parcial progressiva -> "Primeira Despesca", "Segunda Despesca", "Terceira Despesca", ... (ordem cronológica dos eventos).
  - Última despesca que esvazia totalmente o tanque -> "Despesca Final" (preenche colunas de tanques).
  - Eventos parciais (tanque ainda com peixe): colunas Tanques Liberados / Tanques Disponivel ficam VAZIAS.
  - A partir da 1ª despesca: corte SECO do arraçoamento (consumo diário = 0) e peso médio CONGELADO (peixe não cresce mais).
  - Biomassa e mortalidade recalculadas sobre a quantidade restante; linha do tempo encerrada na despesca final/única.

CARGAS:
  - Faixa válida: 7.000 kg <= carga <= 10.000 kg — piso impeditivo, sem exceção.
  - 6.500 kg (PESO_ALERTA_CARGA) apenas como faixa de risco/alerta, não autoriza carga abaixo de 7.000 kg.
  - Resto de tanque < 7.000 kg: tratativa parametrizada (excecao_controlada | deslocar).

Unidades: kg. Entradas em toneladas convertidas em parse_meta_biomassa.
Mês no formato "AAAA-MM" (ex.: 2026-09) — normalizado em _normalizar_mes.
Chave de tanque: (Produtor, Tanque) para evitar colisão de ids entre produtores.
"""
from __future__ import annotations
import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
import pandas as pd

PESO_MIN_DESPESCA = 750.0
CARGA_MIN = 7000.0
CARGA_MAX = 10000.0
PESO_ALERTA_CARGA = 6500.0
SEMANAS_PADRAO = 4
VAZIO_SANITARIO_DIAS = 5
TOL = 1e-6

STATUS_DESPESCA_UNICA = "Despesca Única"
STATUS_DESPESCA_FINAL = "Despesca Final"
STATUS_PRONTO = "Pronto para Despesca"
STATUS_ABAIXO_MINIMO = "Abaixo do Peso Mínimo"

def _status_despesca_ordinal(n: int) -> str:
    ordinais = {1: "Primeira", 2: "Segunda", 3: "Terceira", 4: "Quarta", 5: "Quinta",
                6: "Sexta", 7: "Sétima", 8: "Oitava", 9: "Nona", 10: "Décima",
                11: "Décima Primeira", 12: "Décima Segunda"}
    palavra = ordinais.get(max(int(n), 1), f"{int(n)}ª")
    return f"{palavra} Despesca"

def _normalizar_mes(valor) -> str:
    """Normaliza um mês para 'AAAA-MM'. Aceita 'AAAA-MM', 'MM/AAAA' e 'AAAA/MM'."""
    texto = str(valor).strip()
    if "-" in texto:
        partes = texto.split("-")
        if len(partes) == 2 and len(partes[0]) == 4:
            return f"{partes[0]}-{int(partes[1]):02d}"
    if "/" in texto:
        partes = texto.split("/")
        if len(partes) == 2:
            if len(partes[0]) == 4:
                return f"{partes[0]}-{int(partes[1]):02d}"
            return f"{int(partes[1])}-{int(partes[0]):02d}"
    return texto

def _chave_tanque(produtor, tanque) -> tuple[str, str]:
    return (str(produtor).strip().upper(), str(tanque).strip())

def processar_biomassa_alvo(resultados_simulacao, biomassa_alvo_df, peso_minimo=PESO_MIN_DESPESCA, peso_maximo=None):
    """Encontra a foto de maior peso médio por (mês, produtor, tanque) na faixa de peso."""
    if not resultados_simulacao or biomassa_alvo_df is None or biomassa_alvo_df.empty:
        return pd.DataFrame()
    df = pd.DataFrame(resultados_simulacao)
    df["Data"] = pd.to_datetime(df["Data"], errors="coerce")
    df = df.dropna(subset=["Data"])
    df["Mes"] = df["Data"].dt.strftime("%Y-%m")
    df["Peso Medio (g)"] = pd.to_numeric(df["Peso Medio (g)"], errors="coerce")
    df["Biomassa (kg)"] = pd.to_numeric(df["Biomassa (kg)"], errors="coerce")
    df["Produtor_Norm"] = df["Produtor"].astype(str).str.strip().str.upper()
    produtores_alvo = set(biomassa_alvo_df["Produtor"].astype(str).str.strip().str.upper())
    filtro = (df["Produtor_Norm"].isin(produtores_alvo)) & (df["Peso Medio (g)"] >= peso_minimo)
    if peso_maximo is not None:
        filtro &= df["Peso Medio (g)"] <= peso_maximo
    df_filtrado = df[filtro]
    if df_filtrado.empty:
        return pd.DataFrame()
    idx_max_peso = df_filtrado.groupby(["Mes", "Produtor_Norm", "Tanque"])["Peso Medio (g)"].idxmax()
    df_tanques_disponiveis = df_filtrado.loc[idx_max_peso].copy()
    return df_tanques_disponiveis.sort_values(by=["Mes", "Produtor_Norm", "Peso Medio (g)"], ascending=[True, True, False])

def parse_meta_biomassa(valor):
    """Converte toneladas (string) para kg (float)."""
    try:
        val = str(valor).strip()
        if not val or val.lower() == "none" or val == "nan":
            return 0.0
        return float(val.replace(",", ".")) * 1000.0
    except ValueError:
        return 0.0

def alocar_biomassa(df_tanques_disponiveis, biomassa_alvo_df):
    """Fase 1 (próprio) + Fase 2 (saldo), com carry-over da fração remanescente do tanque entre meses. Retorna (alocacoes, deficits)."""
    if df_tanques_disponiveis.empty or biomassa_alvo_df is None or biomassa_alvo_df.empty:
        return [], []
    alocacoes, deficits = [], []
    pool_tanques = df_tanques_disponiveis.to_dict("records")
    for t in pool_tanques:
        t["Biomassa_Restante_kg"] = float(t["Biomassa (kg)"])
        t["Tanque"] = str(t["Tanque"]).strip()
        t["Original_Biomassa_kg"] = float(t["Biomassa (kg)"])
        t["Chave"] = _chave_tanque(t["Produtor_Norm"], t["Tanque"])
    meses_colunas = sorted((_normalizar_mes(c) for c in biomassa_alvo_df.columns if str(c).strip().lower() != "produtor"), key=lambda m: (int(m.split("-")[0]), int(m.split("-")[1])))
    fracao_restante_por_tanque = {}
    for mes in meses_colunas:
        metas_mes = {}
        for _, row in biomassa_alvo_df.iterrows():
            prod = str(row["Produtor"]).strip().upper()
            meta_kg = parse_meta_biomassa(row.get(_mes_original(biomassa_alvo_df, mes), ""))
            if meta_kg > 0:
                metas_mes[prod] = meta_kg
        tanques_mes = [t for t in pool_tanques if t["Mes"] == mes]
        for t in tanques_mes:
            chave = t["Chave"]
            if chave in fracao_restante_por_tanque:
                f_rest = fracao_restante_por_tanque[chave]
                t["Biomassa_Restante_kg"] = t["Original_Biomassa_kg"] * f_rest
                t["Biomassa (kg)"] = t["Biomassa_Restante_kg"]
        if not metas_mes:
            continue
        tanques_disp = [t for t in tanques_mes if t["Biomassa_Restante_kg"] > TOL]
        for prod, meta_kg in list(metas_mes.items()):
            faltante = meta_kg
            meus_tanques = sorted([t for t in tanques_disp if t["Produtor_Norm"] == prod and t["Biomassa_Restante_kg"] > TOL], key=lambda x: float(x["Peso Medio (g)"]), reverse=True)
            for t in meus_tanques:
                if faltante <= TOL:
                    break
                usado = min(faltante, t["Biomassa_Restante_kg"])
                alocacoes.append({"Mes": mes, "Produtor_Destino": prod, "Produtor_Origem": t["Produtor_Norm"], "Tanque": t["Tanque"], "Volume_kg": usado, "Peso_Medio_g": t["Peso Medio (g)"], "Data_Snapshot": t["Data"], "Tipo_Alocacao": "Fase 1 (Próprio)"})
                t["Biomassa_Restante_kg"] -= usado
                faltante -= usado
                fracao_restante_por_tanque[t["Chave"]] = t["Biomassa_Restante_kg"] / t["Original_Biomassa_kg"] if t["Original_Biomassa_kg"] > 0 else 0.0
            metas_mes[prod] = faltante
        for prod, faltante in metas_mes.items():
            if faltante <= TOL:
                continue
            outros_tanques = sorted([t for t in tanques_disp if t["Biomassa_Restante_kg"] > TOL], key=lambda x: float(x["Peso Medio (g)"]), reverse=True)
            for t in outros_tanques:
                if faltante <= TOL:
                    break
                usado = min(faltante, t["Biomassa_Restante_kg"])
                alocacoes.append({"Mes": mes, "Produtor_Destino": prod, "Produtor_Origem": t["Produtor_Norm"], "Tanque": t["Tanque"], "Volume_kg": usado, "Peso_Medio_g": t["Peso Medio (g)"], "Data_Snapshot": t["Data"], "Tipo_Alocacao": "Fase 2 (Empréstimo)"})
                t["Biomassa_Restante_kg"] -= usado
                faltante -= usado
                fracao_restante_por_tanque[t["Chave"]] = t["Biomassa_Restante_kg"] / t["Original_Biomassa_kg"] if t["Original_Biomassa_kg"] > 0 else 0.0
            if faltante > 0.1:
                deficits.append({"Mes": mes, "Produtor": prod, "Deficit_kg": faltante})
    for i, t in enumerate(pool_tanques):
        df_tanques_disponiveis.loc[df_tanques_disponiveis.index[i], "Biomassa (kg)"] = t["Biomassa (kg)"]
    return alocacoes, deficits

def _mes_original(biomassa_alvo_df, mes_normalizado):
    for c in biomassa_alvo_df.columns:
        if str(c).strip().lower() == "produtor":
            continue
        if _normalizar_mes(c) == mes_normalizado:
            return c
    return mes_normalizado

@dataclass
class FracaoCarga:
    tanque: str
    produtor_origem: str
    volume_kg: float
    peso_medio_g: float
    biomassa_tanque_kg: float
    fracao_removida: float
    restante_apos_kg: float
    esgota_tanque: bool
    data_snapshot: date | None = None

@dataclass
class Carga:
    mes: str
    produtor_destino: str
    fracoes: list[FracaoCarga] = field(default_factory=list)
    semana: int = 0

    @property
    def volume_kg(self) -> float:
        return round(sum(f.volume_kg for f in self.fracoes), 3)

    @property
    def tanques(self) -> list[str]:
        return [f.tanque for f in self.fracoes]

def compor_cargas_parciais(alocacoes, biomassa_total_por_tanque=None, carga_min=CARGA_MIN, carga_max=CARGA_MAX, *, peso_alerta_carga=PESO_ALERTA_CARGA, tratativa_resto="excecao_controlada"):
    """Compoe cargas de 7.000 a 10.000 kg com despesca parcial. Piso impeditivo; resto < 7.000 kg tratado conforme tratativa_resto. Retorna (cargas, alertas)."""
    if tratativa_resto not in {"excecao_controlada", "deslocar"}:
        raise ValueError("tratativa_resto deve ser 'excecao_controlada' ou 'deslocar'")
    alertas = []
    if not alocacoes:
        return [], alertas

    def chave(mes, produtor, tanque):
        return (_normalizar_mes(mes), _chave_tanque(produtor, tanque))

    totais = defaultdict(float)
    for a in alocacoes:
        totais[chave(a["Mes"], a["Produtor_Origem"], a["Tanque"])] += float(a["Volume_kg"])
    if biomassa_total_por_tanque:
        for (mes_c, prod_c, tanque_c), valor in biomassa_total_por_tanque.items():
            c = chave(mes_c, prod_c, tanque_c)
            totais[c] = max(totais[c], float(valor))
    retirado = defaultdict(float)

    def nova_fracao(aloc, volume):
        c = chave(aloc["Mes"], aloc["Produtor_Origem"], aloc["Tanque"])
        tanque = str(aloc["Tanque"]).strip()
        biomassa_total = float(totais.get(c, volume))
        retirado[c] += volume
        restante = biomassa_total - retirado[c]
        return FracaoCarga(tanque=tanque, produtor_origem=str(aloc.get("Produtor_Origem", "")), volume_kg=round(volume, 3), peso_medio_g=float(aloc.get("Peso_Medio_g", 0.0)), biomassa_tanque_kg=round(biomassa_total, 3), fracao_removida=round(volume / biomassa_total, 6) if biomassa_total > 0 else 0.0, restante_apos_kg=round(max(restante, 0.0), 3), esgota_tanque=restante <= TOL, data_snapshot=_coerce_data(aloc.get("Data_Snapshot")))

    cargas = []
    grupos = defaultdict(list)
    for a in alocacoes:
        grupos[(_normalizar_mes(a["Mes"]), str(a["Produtor_Destino"]).strip().upper())].append(a)
    for (mes, destino), alocs in grupos.items():
        alocs_sorted = sorted(alocs, key=lambda a: float(a.get("Peso_Medio_g", 0.0)), reverse=True)
        restos = []
        for aloc in alocs_sorted:
            volume_aloc = float(aloc["Volume_kg"])
            if volume_aloc <= TOL:
                continue
            n_cargas_min = math.ceil(volume_aloc / carga_max)
            pedaco_ideal = volume_aloc / n_cargas_min
            if n_cargas_min > 1 and pedaco_ideal >= carga_min - TOL:
                for _ in range(n_cargas_min):
                    cargas.append(Carga(mes=mes, produtor_destino=destino, fracoes=[nova_fracao(aloc, pedaco_ideal)]))
            else:
                while volume_aloc > carga_max + TOL:
                    cargas.append(Carga(mes=mes, produtor_destino=destino, fracoes=[nova_fracao(aloc, carga_max)]))
                    volume_aloc -= carga_max
                if volume_aloc > TOL:
                    frac = nova_fracao(aloc, volume_aloc)
                    if frac.volume_kg >= carga_min - TOL:
                        cargas.append(Carga(mes=mes, produtor_destino=destino, fracoes=[frac]))
                    else:
                        restos.append(frac)
        restos.sort(key=lambda f: f.volume_kg, reverse=True)
        while restos:
            carga = Carga(mes=mes, produtor_destino=destino)
            capacidade = carga_max
            usados = []
            for frac in restos:
                if frac.volume_kg <= capacidade + TOL:
                    carga.fracoes.append(frac)
                    usados.append(frac)
                    capacidade -= frac.volume_kg
                    if capacidade <= TOL:
                        break
            for f in usados:
                restos.remove(f)
            if not carga.fracoes:
                break
            if carga.volume_kg >= carga_min - TOL:
                cargas.append(carga)
                continue
            alerta_base = {"mes": mes, "produtor_destino": destino, "volume_kg": carga.volume_kg, "tanques": carga.tanques}
            if carga.volume_kg < peso_alerta_carga - TOL:
                alertas.append({**alerta_base, "tipo": "alerta_risco_6500"})
            if tratativa_resto == "deslocar":
                alertas.append({**alerta_base, "tipo": "resto_deslocado_proxima_despesca"})
            else:
                cargas.append(carga)
                alertas.append({**alerta_base, "tipo": "excecao_controlada_abaixo_minimo"})
    return cargas, alertas

def distribuir_semanas_parciais(cargas, volume_por_destino=None, semanas=SEMANAS_PADRAO):
    """Distribui cargas nas semanas do mes. Quota semanal; tanque parcial nao repete semana; ultimo recurso = semana de menor acumulo."""
    if not cargas or semanas <= 0:
        return cargas
    uso_por_tanque = defaultdict(set)
    grupos = defaultdict(list)
    for c in cargas:
        grupos[(c.mes, c.produtor_destino)].append(c)
    resultado = []
    for (mes, destino), lista in grupos.items():
        quota_total = 0.0
        if volume_por_destino is not None:
            quota_total = float(volume_por_destino.get((mes, destino), 0.0) or 0.0)
        soma = sum(c.volume_kg for c in lista)
        quota = (quota_total / semanas) if quota_total > 0 else (soma / semanas)
        lista.sort(key=lambda c: max((f.peso_medio_g for f in c.fracoes), default=0.0), reverse=True)
        acumulado = [0.0] * (semanas + 1)
        for carga in lista:
            tanques = {_chave_tanque(f.produtor_origem, f.tanque) for f in carga.fracoes}
            escolhida = 0
            for s in range(1, semanas + 1):
                if acumulado[s] + carga.volume_kg > quota + TOL:
                    continue
                if any(s in uso_por_tanque[t] for t in tanques):
                    continue
                escolhida = s
                break
            if escolhida == 0:
                for s in range(1, semanas + 1):
                    if any(s in uso_por_tanque[t] for t in tanques):
                        continue
                    escolhida = s
                    break
            if escolhida == 0:
                escolhida = min(range(1, semanas + 1), key=lambda s: acumulado[s])
            carga.semana = escolhida
            acumulado[escolhida] += carga.volume_kg
            for t in tanques:
                uso_por_tanque[t].add(escolhida)
        resultado.extend(lista)
    return resultado

def eventos_por_tanque(cargas):
    """Linha do tempo de eventos por tanque (chave Produtor,Tanque) com ordinal, unica e final."""
    eventos = defaultdict(list)
    ocorrencias = defaultdict(int)
    for c in cargas:
        for f in c.fracoes:
            ocorrencias[_chave_tanque(f.produtor_origem, f.tanque)] += 1
    for c in cargas:
        for f in c.fracoes:
            chave = _chave_tanque(f.produtor_origem, f.tanque)
            usar_snapshot = ocorrencias[chave] == 1
            eventos[chave].append({"mes": c.mes, "semana": c.semana, "data": _data_do_evento(f, c.mes, c.semana, usar_snapshot), "volume_kg": f.volume_kg, "fracao_removida": f.fracao_removida, "restante_apos_kg": f.restante_apos_kg, "peso_medio_g": f.peso_medio_g, "esgota_tanque": f.esgota_tanque})
    for chave, evs in eventos.items():
        evs.sort(key=lambda e: e["data"])
        total = len(evs)
        esgotado = evs[-1]["esgota_tanque"]
        for i, e in enumerate(evs, start=1):
            e["ordinal"] = i
            e["total"] = total
            e["unica"] = esgotado and total == 1
            e["final"] = esgotado and (i == total)
    return dict(eventos)

def aplicar_despesca_parcial_no_relatorio(resultados_simulacao, cargas, *, peso_minimo=PESO_MIN_DESPESCA, vazio_sanitario_dias=VAZIO_SANITARIO_DIAS, encerrar_linha_do_tempo=True):
    """Aplica a linha do tempo de despesca sobre o relatorio. Status Unica/Final decididos por esgota_tanque. Corte seco, peso congelado, biomassa e mortalidade recalculadas."""
    eventos = eventos_por_tanque(cargas)
    if not resultados_simulacao:
        return []
    saida = [dict(r) for r in resultados_simulacao]
    for reg in saida:
        tanque = str(reg.get("Tanque", "")).strip()
        produtor = str(reg.get("Produtor", "")).strip().upper()
        chave = _chave_tanque(produtor, tanque)
        evs = eventos.get(chave)
        if not evs:
            continue
        data_reg = _coerce_data(reg.get("Data"))
        if data_reg is None:
            continue
        pm_original = _to_float(reg.get("Peso Medio (g)"))
        q_original = _to_float(reg.get("Quantidade de Peixes"))
        ocorridos = [e for e in evs if e["data"] <= data_reg]
        if not ocorridos:
            reg["Status"] = STATUS_ABAIXO_MINIMO if pm_original < peso_minimo else STATUS_PRONTO
            continue
        ultimo = ocorridos[-1]
        if ultimo["unica"]:
            reg["Status"] = STATUS_DESPESCA_UNICA
        elif ultimo["final"]:
            reg["Status"] = STATUS_DESPESCA_FINAL
        else:
            reg["Status"] = _status_despesca_ordinal(ultimo["ordinal"])
        fracao_ocorrida = sum(e["fracao_removida"] for e in ocorridos)
        frac_restante = max(1.0 - fracao_ocorrida, 0.0)
        q_restante = round(q_original * frac_restante, 2)
        reg["Quantidade de Peixes"] = q_restante
        
        # O peixe que sobra continua crescendo (não congelamos o Peso Medio original)
        reg["Biomassa (kg)"] = round(q_restante * pm_original / 1000.0, 2)
        
        if "Consumo de Racao Diario (kg)" in reg:
            rc_orig = _to_float(reg.get("Consumo de Racao Diario (kg)"))
            reg["Consumo de Racao Diario (kg)"] = round(rc_orig * frac_restante, 2)
        if "Custo de Racao Diario" in reg:
            custo_orig = _to_float(reg.get("Custo de Racao Diario"))
            reg["Custo de Racao Diario"] = round(custo_orig * frac_restante, 2)
        mort_orig = _to_float(reg.get("Mortalidade Diaria (peixes)"))
        reg["Mortalidade Diaria (peixes)"] = round(mort_orig * frac_restante, 2)
        if ultimo["unica"] or ultimo["final"]:
            liberado = ultimo["data"] + timedelta(days=1)
            reg["Tanques Liberados"] = liberado.strftime("%d/%m/%Y")
            reg["Tanques Disponivel"] = (liberado + timedelta(days=vazio_sanitario_dias)).strftime("%d/%m/%Y")
        else:
            reg["Tanques Liberados"] = ""
            reg["Tanques Disponivel"] = ""
        reg["_frac_restante"] = frac_restante
        reg["_q_restante"] = q_restante
    indices_por_tanque = defaultdict(list)
    for i, reg in enumerate(saida):
        indices_por_tanque[_chave_tanque(str(reg.get("Produtor", "")), str(reg.get("Tanque", "")))].append(i)
    for chave, idxs in indices_por_tanque.items():
        if chave not in eventos:
            continue
        q_inicial = _to_float(saida[idxs[0]].get("Quantidade de Peixes"))
        mort_acum = 0.0
        for i in idxs:
            reg = saida[i]
            q_atual = _to_float(reg.get("Quantidade de Peixes"))
            mort_dia = _to_float(reg.get("Mortalidade Diaria (peixes)"))
            mort_acum += mort_dia
            reg["Mortalidade Acumulada (peixes)"] = round(mort_acum, 2)
            q_antes = q_atual + mort_dia
            sobrev_dia = 100.0 - (mort_dia / q_antes * 100.0) if q_antes > 0 else 100.0
            reg["Sobrevivencia Diaria (%)"] = round(sobrev_dia, 6)
            
            frac = reg.get("_frac_restante", 1.0)
            q_inicial_eff = q_inicial * frac
            reg["Sobrevivencia Acumulada (%)"] = round(q_atual / q_inicial_eff * 100.0, 6) if q_inicial_eff > 0 else 100.0
            
            reg.pop("_frac_restante", None)
            reg.pop("_q_restante", None)
    if encerrar_linha_do_tempo:
        data_corte = {}
        for chave, evs in eventos.items():
            if evs[-1]["unica"] or evs[-1]["final"]:
                data_corte[chave] = evs[-1]["data"] + timedelta(days=1)
        saida = [
            reg for reg in saida 
            if not (
                (chave := _chave_tanque(str(reg.get("Produtor", "")), str(reg.get("Tanque", "")))) in data_corte
                and (data_reg := _coerce_data(reg.get("Data"))) is not None 
                and data_reg >= data_corte[chave]
            )
        ]
    return saida

def gerar_relatorio_sobras_faltas(df_tanques_disponiveis: pd.DataFrame, biomassa_alvo_df: pd.DataFrame, alocacoes: list[dict]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Relatório de fechamento com drill-down: Alvo x Disponível x Alocado x Recebido x Sobra x Falta por produtor/mês."""
    if df_tanques_disponiveis.empty or biomassa_alvo_df.empty:
        return pd.DataFrame(), pd.DataFrame()
        
    meses_colunas = sorted((_normalizar_mes(c) for c in biomassa_alvo_df.columns if str(c).strip().lower() != "produtor"), key=lambda m: (int(m.split("-")[0]), int(m.split("-")[1])))
    
    detalhes = []
    disp_mensal = defaultdict(float)
    pool_tanques = df_tanques_disponiveis.to_dict("records")
    
    tanques_disp_por_mes_prod = defaultdict(list)
    for t in pool_tanques:
        mes = str(t.get("Mes", "")).strip()
        prod = str(t.get("Produtor_Norm", "")).strip().upper()
        vol_disp = _to_float(t.get("Biomassa (kg)", 0.0))
        if vol_disp > 0:
            disp_mensal[(mes, prod)] += vol_disp
            tanques_disp_por_mes_prod[(mes, prod)].append({
                "Tanque": str(t.get("Tanque", "")).strip(),
                "Volume": vol_disp
            })

    alocacoes_por_mes_origem = defaultdict(list)
    for a in alocacoes:
        mes = str(a.get("Mes", "")).strip()
        origem = str(a.get("Produtor_Origem", "")).strip().upper()
        alocacoes_por_mes_origem[(mes, origem)].append(a)
    
    resumo = []
    for mes in meses_colunas:
        for _, row in biomassa_alvo_df.iterrows():
            prod = str(row["Produtor"]).strip().upper()
            meta_kg = parse_meta_biomassa(row.get(_mes_original(biomassa_alvo_df, mes), ""))
            
            disp = disp_mensal.get((mes, prod), 0.0)
            alocs = alocacoes_por_mes_origem.get((mes, prod), [])
            aloc_propria = sum(a["Volume_kg"] for a in alocs if a["Tipo_Alocacao"] == "Fase 1 (Próprio)")
            aloc_terceiros = sum(a["Volume_kg"] for a in alocs if a["Tipo_Alocacao"] == "Fase 2 (Empréstimo)")
            aloc_total = aloc_propria + aloc_terceiros
            
            sobra = max(disp - aloc_total, 0.0)
            falta = max(meta_kg - aloc_total, 0.0)
            
            if meta_kg > 0 or disp > 0 or aloc_total > 0:
                resumo.append({
                    "Mês": mes,
                    "Produtor": prod,
                    "Biomassa Alvo": round(meta_kg, 2),
                    "Disponível": round(disp, 2),
                    "Alocação Própria": round(aloc_propria, 2),
                    "Alocação p/ Terceiros": round(aloc_terceiros, 2),
                    "Alocação Total": round(aloc_total, 2),
                    "Sobra de Biomassa Pronta": round(sobra, 2),
                    "Biomassa que faltou para a Meta": round(falta, 2)
                })
                
                for t in tanques_disp_por_mes_prod.get((mes, prod), []):
                    tanque_id = t["Tanque"]
                    disp_tanque = t["Volume"]
                    
                    alocs_tanque = [a for a in alocs if a["Tanque"] == tanque_id]
                    propria_tanque = sum(a["Volume_kg"] for a in alocs_tanque if a["Tipo_Alocacao"] == "Fase 1 (Próprio)")
                    terceiros_tanque = sum(a["Volume_kg"] for a in alocs_tanque if a["Tipo_Alocacao"] == "Fase 2 (Empréstimo)")
                    total_tanque = propria_tanque + terceiros_tanque
                    sobra_tanque = max(disp_tanque - total_tanque, 0.0)
                    
                    destinos_terceiros = [a["Produtor_Destino"] for a in alocs_tanque if a["Tipo_Alocacao"] == "Fase 2 (Empréstimo)"]
                    destino_str = ", ".join(set(destinos_terceiros)) if destinos_terceiros else ""
                    
                    detalhes.append({
                        "Mês": mes,
                        "Produtor de Origem": prod,
                        "Tanque": tanque_id,
                        "Biomassa disponível do tanque": round(disp_tanque, 2),
                        "Biomassa alocada para o próprio produtor": round(propria_tanque, 2),
                        "Biomassa alocada para terceiros": round(terceiros_tanque, 2),
                        "Produtor de Destino": destino_str,
                        "Alocação Total do tanque": round(total_tanque, 2),
                        "Biomassa restante/sobra do tanque": round(sobra_tanque, 2)
                    })

    return pd.DataFrame(resumo), pd.DataFrame(detalhes)

def executar_planejamento_despesca(resultados_simulacao, biomassa_alvo_df, *, peso_minimo=PESO_MIN_DESPESCA, peso_maximo=None, semanas=SEMANAS_PADRAO, carga_min=CARGA_MIN, carga_max=CARGA_MAX, tolerancia_pct=5.0, vazio_sanitario_dias=VAZIO_SANITARIO_DIAS, biomassa_total_por_tanque=None, tratativa_resto="excecao_controlada", encerrar_linha_do_tempo=True):
    """Pipeline completo."""
    df_disp = processar_biomassa_alvo(resultados_simulacao, biomassa_alvo_df, peso_minimo, peso_maximo)
    alocacoes, deficits = alocar_biomassa(df_disp, biomassa_alvo_df)
    volume_por_destino = _metas_por_destino(biomassa_alvo_df)
    # Calcular o peso de alerta (ex: se carga_max = 10000 e tolerancia_pct = 5, = 9500)
    alerta_carga = carga_max * (1.0 - (tolerancia_pct / 100.0))
    
    cargas, alertas = compor_cargas_parciais(
        alocacoes, 
        biomassa_total_por_tanque=biomassa_total_por_tanque, 
        carga_min=carga_min, 
        carga_max=carga_max, 
        peso_alerta_carga=alerta_carga,
        tratativa_resto=tratativa_resto
    )
    cargas = distribuir_semanas_parciais(cargas, volume_por_destino=volume_por_destino, semanas=semanas)
    relatorio = aplicar_despesca_parcial_no_relatorio(resultados_simulacao, cargas, peso_minimo=peso_minimo, vazio_sanitario_dias=vazio_sanitario_dias, encerrar_linha_do_tempo=encerrar_linha_do_tempo)
    df_sobras, df_detalhes = gerar_relatorio_sobras_faltas(df_disp, biomassa_alvo_df, alocacoes)
    return {"relatorio": relatorio, "tanques_disponiveis": df_disp, "alocacoes": alocacoes, "deficits": deficits, "cargas": cargas, "alertas": alertas, "sobras_faltas": df_sobras, "detalhe_sobras_faltas": df_detalhes}

def _metas_por_destino(biomassa_alvo_df):
    metas = {}
    if biomassa_alvo_df is None or biomassa_alvo_df.empty:
        return metas
    for _, row in biomassa_alvo_df.iterrows():
        prod = str(row["Produtor"]).strip().upper()
        for c in biomassa_alvo_df.columns:
            if str(c).strip().lower() == "produtor":
                continue
            mes = _normalizar_mes(c)
            meta_kg = parse_meta_biomassa(row.get(c, ""))
            if meta_kg > 0:
                metas[(mes, prod)] = meta_kg
    return metas

def _data_do_evento(frac, mes, semana, usar_snapshot):
    if usar_snapshot and frac.data_snapshot is not None:
        return frac.data_snapshot
    return _data_no_meio_da_semana(mes, semana)

def _data_no_meio_da_semana(mes, semana):
    try:
        ano, num_mes = (int(x) for x in str(mes).split("-"))
    except ValueError:
        return date.today()
    primeiro = date(ano, num_mes, 1)
    if num_mes == 12:
        ultimo = date(ano + 1, 1, 1) - timedelta(days=1)
    else:
        ultimo = date(ano, num_mes + 1, 1) - timedelta(days=1)
    dia = 1 + (semana - 1) * 7 + 3
    return min(date(ano, num_mes, dia), ultimo)

def _coerce_data(valor):
    if valor is None:
        return None
    if isinstance(valor, pd.Timestamp):
        return None if pd.isna(valor) else valor.date()
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    texto = str(valor).strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d/%m/%y", "%d-%m-%Y"):
        try:
            return datetime.strptime(texto, fmt).date()
        except ValueError:
            continue
    return None

def _to_float(valor):
    try:
        f = float(valor)
        return f if math.isfinite(f) else 0.0
    except (TypeError, ValueError):
        return 0.0
