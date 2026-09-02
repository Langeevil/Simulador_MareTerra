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
    
    df_filtrado = df[
        (df['Produtor_Norm'].isin(produtores_alvo)) &
        (df['Peso Medio (g)'] >= peso_minimo) &
        (df['Peso Medio (g)'] <= peso_maximo)
    ]
    
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
