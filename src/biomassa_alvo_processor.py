import pandas as pd
from datetime import date
import copy

def processar_biomassa_alvo(
    resultados_simulacao: list[dict],
    biomassa_alvo_df: pd.DataFrame,
    peso_minimo: float,
    peso_maximo: float
) -> pd.DataFrame:
    """
    Tópico 1: Encontra a 'foto' de maior peso médio para cada tanque dentro da faixa.
    """
    if not resultados_simulacao or biomassa_alvo_df is None or biomassa_alvo_df.empty:
        return pd.DataFrame()

    df = pd.DataFrame(resultados_simulacao)
    df['Data'] = pd.to_datetime(df['Data'])
    df['Mes'] = df['Data'].dt.strftime('%Y-%m')
    
    df['Peso Medio (g)'] = pd.to_numeric(df['Peso Medio (g)'], errors='coerce')
    df['Biomassa (kg)'] = pd.to_numeric(df['Biomassa (kg)'], errors='coerce')
    df['Produtor_Norm'] = df['Produtor'].astype(str).str.strip().str.upper()
    
    produtores_alvo = set(biomassa_alvo_df['Produtor'].astype(str).str.strip().str.upper())
    
    condicao = (df['Produtor_Norm'].isin(produtores_alvo)) & (df['Peso Medio (g)'] >= peso_minimo)
    if peso_maximo > 0:
        condicao &= (df['Peso Medio (g)'] <= peso_maximo)
        
    df_filtrado = df[condicao]
    
    if df_filtrado.empty:
        return pd.DataFrame()

    idx_max_peso = df_filtrado.groupby(['Mes', 'Produtor_Norm', 'Tanque'])['Peso Medio (g)'].idxmax()
    df_tanques_disponiveis = df_filtrado.loc[idx_max_peso].copy()
    
    # Ordena por Mês, Produtor e Peso Médio (decrescente)
    df_tanques_disponiveis = df_tanques_disponiveis.sort_values(
        by=['Mes', 'Produtor_Norm', 'Peso Medio (g)'], 
        ascending=[True, True, False]
    )
    
    return df_tanques_disponiveis


def parse_meta_biomassa(valor: str) -> float:
    """Converte valor da interface (toneladas string) para kg (float)"""
    try:
        val = str(valor).strip()
        if not val or val.lower() == 'none' or val == 'nan':
            return 0.0
        val = val.replace(',', '.')
        return float(val) * 1000.0  # toneladas -> kg
    except ValueError:
        return 0.0


def alocar_biomassa(
    df_tanques_disponiveis: pd.DataFrame, 
    biomassa_alvo_df: pd.DataFrame
) -> tuple[list[dict], list[dict]]:
    """
    Tópico 2: Aloca os tanques em duas fases.
    Fase 1: Cada produtor usa seus próprios tanques primeiro.
    Fase 2: O que faltar (déficit) é pego dos tanques restantes de outros produtores.
    
    Retorna (alocacoes, deficits).
    """
    if df_tanques_disponiveis.empty or biomassa_alvo_df is None or biomassa_alvo_df.empty:
        return [], []

    alocacoes = []
    deficits = []
    
    # Prepara o pool de tanques convertendo para lista de dicionários para facilitar manipulação de saldo
    pool_tanques = df_tanques_disponiveis.to_dict('records')
    for t in pool_tanques:
        t['Biomassa_Restante_kg'] = t['Biomassa (kg)']
        
    meses_colunas = [c for c in biomassa_alvo_df.columns if c != 'Produtor']
    
    for mes in meses_colunas:
        # Pega as metas do mês
        metas_mes = {}
        for _, row in biomassa_alvo_df.iterrows():
            prod = str(row['Produtor']).strip().upper()
            meta_kg = parse_meta_biomassa(row.get(mes, ""))
            if meta_kg > 0:
                metas_mes[prod] = meta_kg
                
        if not metas_mes:
            continue
            
        tanques_mes = [t for t in pool_tanques if t['Mes'] == mes and t['Biomassa_Restante_kg'] > 0]
        
        # ---------------------------------------------------------
        # FASE 1: Cada um usa seus próprios tanques
        # ---------------------------------------------------------
        for prod, meta_kg in metas_mes.items():
            faltante = meta_kg
            # Pega tanques do produtor, ordenados pelo mais pesado (já vêm ordenados do Tópico 1, mas garantimos aqui)
            meus_tanques = [t for t in tanques_mes if t['Produtor_Norm'] == prod and t['Biomassa_Restante_kg'] > 0]
            meus_tanques.sort(key=lambda x: x['Peso Medio (g)'], reverse=True)
            
            for t in meus_tanques:
                if faltante <= 0:
                    break
                
                disponivel = t['Biomassa_Restante_kg']
                usado = min(faltante, disponivel)
                
                alocacoes.append({
                    'Mes': mes,
                    'Produtor_Destino': prod,
                    'Produtor_Origem': t['Produtor_Norm'],
                    'Tanque': t['Tanque'],
                    'Volume_kg': usado,
                    'Peso_Medio_g': t['Peso Medio (g)'],
                    'Data_Snapshot': t['Data'],
                    'Tipo_Alocacao': 'Fase 1 (Próprio)'
                })
                
                t['Biomassa_Restante_kg'] -= usado
                faltante -= usado
                
            metas_mes[prod] = faltante # Atualiza o que ainda falta bater

        # ---------------------------------------------------------
        # FASE 2: A Xepa (Empréstimo de Terceiros)
        # ---------------------------------------------------------
        for prod, faltante in metas_mes.items():
            if faltante <= 0:
                continue
                
            # Busca em TODOS os tanques que ainda tem saldo no mês, independente do dono
            outros_tanques = [t for t in tanques_mes if t['Biomassa_Restante_kg'] > 0]
            # Ordena globalmente pelo peixe mais pesado
            outros_tanques.sort(key=lambda x: x['Peso Medio (g)'], reverse=True)
            
            for t in outros_tanques:
                if faltante <= 0:
                    break
                    
                disponivel = t['Biomassa_Restante_kg']
                usado = min(faltante, disponivel)
                
                alocacoes.append({
                    'Mes': mes,
                    'Produtor_Destino': prod,
                    'Produtor_Origem': t['Produtor_Norm'],
                    'Tanque': t['Tanque'],
                    'Volume_kg': usado,
                    'Peso_Medio_g': t['Peso Medio (g)'],
                    'Data_Snapshot': t['Data'],
                    'Tipo_Alocacao': 'Fase 2 (Empréstimo)'
                })
                
                t['Biomassa_Restante_kg'] -= usado
                faltante -= usado
                
            # Registra se mesmo após a Xepa o cara ficou devendo
            if faltante > 0.1: # Margem de erro float
                deficits.append({
                    'Mes': mes,
                    'Produtor': prod,
                    'Deficit_kg': faltante
                })

    return alocacoes, deficits

def empacotar_cargas(alocacoes: list[dict], semanas: int = 4) -> list[dict]:
    """
    Tópico 3: Bin-Packing de Caminhões (7t e 10t).
    Pega todas as alocações brutas, divide por produtor e mês, e distribui
    a biomassa em 4 semanas formando cargas exatas.
    O que sobrar no final (ex: < 7t) é ignorado neste mês (não vira carga).
    """
    cargas_finais = []
    
    alocacoes_agrupadas = {}
    for a in alocacoes:
        chave = (a['Mes'], a['Produtor_Destino'])
        if chave not in alocacoes_agrupadas:
            alocacoes_agrupadas[chave] = []
        alocacoes_agrupadas[chave].append(a)
        
    for (mes, produtor), lista_aloc in alocacoes_agrupadas.items():
        fila = []
        for a in lista_aloc:
            fila.append({
                'tanque': a['Tanque'], 
                'origem': a['Produtor_Origem'], 
                'volume': a['Volume_kg'], 
                'pm': a['Peso_Medio_g'],
                'data': a['Data_Snapshot']
            })
            
        volume_total = sum(f['volume'] for f in fila)
        quota_semanal = volume_total / semanas
        saldo_carry = 0
        
        for semana in range(1, semanas + 1):
            meta_semana = quota_semanal + saldo_carry
            volume_semana_atual = 0
            
            while volume_semana_atual + 7000 <= meta_semana + 2500:
                estoque_restante = sum(f['volume'] for f in fila)
                
                if volume_semana_atual + 10000 <= meta_semana + 2500 and estoque_restante >= 10000:
                    tamanho_carga = 10000
                elif estoque_restante >= 7000:
                    tamanho_carga = 7000
                else:
                    break
                    
                carga_atual = {
                    'Mes': mes,
                    'Semana': semana,
                    'Produtor_Destino': produtor,
                    'Tamanho_Carga_kg': tamanho_carga,
                    'Composicao': []
                }
                
                falta_na_carga = tamanho_carga
                
                while falta_na_carga > 0.1 and fila:
                    chunk = fila[0]
                    usado = min(chunk['volume'], falta_na_carga)
                    
                    carga_atual['Composicao'].append({
                        'Tanque': chunk['tanque'],
                        'Produtor_Origem': chunk['origem'],
                        'Volume_kg': usado,
                        'Peso_Medio_g': chunk['pm'],
                        'Data_Snapshot': chunk['data']
                    })
                    
                    falta_na_carga -= usado
                    chunk['volume'] -= usado
                    
                    if chunk['volume'] < 0.1:
                        fila.pop(0)
                        
                cargas_finais.append(carga_atual)
                volume_semana_atual += tamanho_carga
                
            saldo_carry = meta_semana - volume_semana_atual
            
    return cargas_finais


from datetime import timedelta

def aplicar_despesca_no_relatorio(resultados_simulacao: list[dict], cargas_finais: list[dict]) -> list[dict]:
    """
    Tópico 4: Integra a decisão de despesca no relatório final.
    - Atualiza o Status para 'Despescado'.
    - Congela o tanque (remove linhas de dias posteriores ao snapshot, para não cobrar ração).
    - Marca Tanques Liberados e Tanques Disponivel.
    """
    # Monta um dicionário rápido: (Produtor, Tanque) -> Data de Despesca
    tanques_despescados = {}
    for carga in cargas_finais:
        for comp in carga['Composicao']:
            produtor_origem = comp['Produtor_Origem']
            tanque = comp['Tanque']
            data_despesca = comp['Data_Snapshot']
            if isinstance(data_despesca, str):
                data_despesca = pd.to_datetime(data_despesca).date()
            elif isinstance(data_despesca, pd.Timestamp):
                data_despesca = data_despesca.date()
                
            chave = (produtor_origem.upper(), tanque.upper())
            # Se um tanque foi parcialmente despescado em vários dias, 
            # pegamos a ÚLTIMA data como a data final de liberação
            if chave not in tanques_despescados or data_despesca > tanques_despescados[chave]:
                tanques_despescados[chave] = data_despesca

    resultados_atualizados = []
    
    for row in resultados_simulacao:
        produtor = str(row.get('Produtor', '')).strip().upper()
        tanque = str(row.get('Tanque', '')).strip().upper()
        data_row = row['Data']
        
        chave = (produtor, tanque)
        if chave in tanques_despescados:
            data_despesca = tanques_despescados[chave]
            
            # Se a linha for POSTERIOR à data de despesca, cortamos fora!
            # Assim ele não consome ração nem ganha peso no mês seguinte
            if data_row > data_despesca:
                continue
                
            # Se for EXATAMENTE o dia da despesca
            if data_row == data_despesca:
                row['Status'] = 'Despescado'
                row['Tanques Liberados'] = data_despesca.strftime('%d/%m/%Y')
                row['Tanques Disponivel'] = (data_despesca + timedelta(days=5)).strftime('%d/%m/%Y')

        resultados_atualizados.append(row)

    return resultados_atualizados

def gerar_relatorio_sobras_faltas(
    df_tanques_disponiveis: pd.DataFrame, 
    biomassa_alvo_df: pd.DataFrame, 
    cargas_finais: list[dict]
) -> pd.DataFrame:
    """
    Gera um relatório comparando a Meta vs Disponível vs Realizado.
    Sobra = Biomassa Inicial Disponível do Produtor - Biomassa que saiu dos tanques dele
    Falta = Meta do Produtor - Biomassa que ele recebeu para atingir a meta
    """
    resumo = []
    
    if df_tanques_disponiveis.empty or biomassa_alvo_df.empty:
        return pd.DataFrame()
        
    meses_colunas = [c for c in biomassa_alvo_df.columns if c != 'Produtor']
    
    # 1. Agrupar total disponível por Produtor e Mês
    disp_mensal = df_tanques_disponiveis.groupby(['Mes', 'Produtor_Norm'])['Biomassa (kg)'].sum().to_dict()
    
    # 2. Agrupar total doado (saída) e recebido (entrada) por Produtor e Mês
    doado_mensal = {}
    recebido_mensal = {}
    
    for c in cargas_finais:
        mes = c['Mes']
        dest = c['Produtor_Destino']
        
        for comp in c['Composicao']:
            orig = comp['Produtor_Origem']
            vol = comp['Volume_kg']
            
            doado_mensal[(mes, orig)] = doado_mensal.get((mes, orig), 0) + vol
            recebido_mensal[(mes, dest)] = recebido_mensal.get((mes, dest), 0) + vol
            
    # 3. Construir o relatório
    for mes in meses_colunas:
        for _, row in biomassa_alvo_df.iterrows():
            prod = str(row['Produtor']).strip().upper()
            meta_kg = parse_meta_biomassa(row.get(mes, ""))
            
            disp = disp_mensal.get((mes, prod), 0.0)
            doado = doado_mensal.get((mes, prod), 0.0)
            recebido = recebido_mensal.get((mes, prod), 0.0)
            
            sobra = disp - doado
            falta = meta_kg - recebido
            
            # Tratamento de imprecisões de float
            if sobra < 1.0: sobra = 0.0
            if falta < 1.0: falta = 0.0
            
            # Só adiciona se houver alguma interação no mês (meta, disponivel, ou algo recebido)
            if meta_kg > 0 or disp > 0 or recebido > 0:
                resumo.append({
                    'Mês': mes,
                    'Produtor': prod,
                    'Biomassa Alvo (kg)': round(meta_kg, 2),
                    'Disponível Inicial (kg)': round(disp, 2),
                    'Alocado p/ Propria Meta e Terceiros (kg)': round(doado, 2),
                    'Recebido Total (kg)': round(recebido, 2),
                    'Sobra no Tanque (kg)': round(sobra, 2),
                    'Falta para Meta (kg)': round(falta, 2)
                })
                
    return pd.DataFrame(resumo)

