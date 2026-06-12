import pandas as pd
import numpy as np

def aplicar_overrides_peso_medio(df_base: pd.DataFrame, overrides: dict[str, dict[str, float]]) -> pd.DataFrame:
    """
    Applies user-defined average weight overrides to the dataset.
    overrides format: { 'regiao_calc': { 'produtor': { 'mes': novo_peso_g } } }
    """
    df = df_base.copy()
    
    # Iterate through overrides
    for regiao, produtores in overrides.items():
        for produtor, meses in produtores.items():
            for mes, novo_peso in meses.items():
                if pd.isna(novo_peso) or novo_peso <= 0:
                    continue
                    
                # O UI envia a coluna como "MM/YYYY", mas o df_base['mes'] é "YYYY-MM"
                mes_norm = mes
                if "/" in mes:
                    partes = mes.split("/")
                    if len(partes) == 2:
                        mes_norm = f"{partes[1]}-{partes[0].zfill(2)}"
                    
                # 1. Encontra os tanques do produtor que possuem registro no mês especificado
                tanques_no_mes = df.loc[
                    (df['regiao_calc'] == regiao) & 
                    (df['produtor'] == produtor) & 
                    (df['mes'] == mes_norm), 'tanque'
                ].unique()

                for t in tanques_no_mes:
                    # 2. Pega todas as linhas desse tanque específico
                    mask_tanque = (df['regiao_calc'] == regiao) & (df['produtor'] == produtor) & (df['tanque'] == t)
                    
                    if not mask_tanque.any():
                        continue
                        
                    df_tanque = df[mask_tanque]
                    
                    # 2.5 Extrapolador Matemático para pesos > 900g
                    peso_maximo = df_tanque['peso_medio_g'].max()
                    if float(novo_peso) > peso_maximo:
                        from datetime import timedelta
                        df_tanque_sorted = df_tanque.sort_values('data')
                        ultima_linha = df_tanque_sorted.iloc[-1].copy()
                        
                        # Calcula GPD dos últimos dias
                        if len(df_tanque_sorted) >= 2:
                            penultima = df_tanque_sorted.iloc[-2]
                            dias = (ultima_linha['data'] - penultima['data']).days
                            gdp = (ultima_linha['peso_medio_g'] - penultima['peso_medio_g']) / dias if dias > 0 else 3.0
                        else:
                            gdp = 3.0
                            
                        if gdp <= 0: gdp = 3.0
                        
                        peso_faltante = float(novo_peso) - peso_maximo
                        dias_extras = int(round(peso_faltante / gdp))
                        
                        nova_linha = ultima_linha.copy()
                        nova_linha['data'] = ultima_linha['data'] + timedelta(days=dias_extras)
                        nova_linha['peso_medio_g'] = float(novo_peso)
                        
                        # Recalcula biomassa usando a proporção do peso (mantendo a qtde de peixes constante)
                        if peso_maximo > 0:
                            nova_linha['biomassa_kg'] = (ultima_linha['biomassa_kg'] / peso_maximo) * float(novo_peso)
                            
                        # Insere no DataFrame principal e atualiza as variáveis
                        df = pd.concat([df, pd.DataFrame([nova_linha])], ignore_index=True)
                        mask_tanque = (df['regiao_calc'] == regiao) & (df['produtor'] == produtor) & (df['tanque'] == t)
                        df_tanque = df[mask_tanque]

                    # 3. Encontra a linha (índice) onde o peso_medio_g é o MAIS PRÓXIMO do novo_peso
                    diffs = (df_tanque['peso_medio_g'] - float(novo_peso)).abs()
                    idx_mais_proximo = diffs.idxmin()
                    
                    # 4. Marca como Peixe Pronto (mantendo o peso e biomassa originais)
                    df.loc[idx_mais_proximo, 'status'] = 'Peixe Pronto'
                    
                    from datetime import timedelta
                    vazio_sanitario_dias = 5
                    
                    if 'tanques_liberados' in df.columns:
                        df['tanques_liberados'] = df['tanques_liberados'].astype(object)
                    if 'tanques_disponivel' in df.columns:
                        df['tanques_disponivel'] = df['tanques_disponivel'].astype(object)
                        
                    dt_escolhida = df.loc[idx_mais_proximo, 'data']
                    if pd.notnull(dt_escolhida):
                        df.loc[idx_mais_proximo, 'tanques_liberados'] = (dt_escolhida + timedelta(days=1)).strftime("%d/%m/%Y")
                        df.loc[idx_mais_proximo, 'tanques_disponivel'] = (dt_escolhida + timedelta(days=1 + vazio_sanitario_dias)).strftime("%d/%m/%Y")
                        
                    # 5. Deleta TODAS as linhas desse tanque onde a data for posterior à escolhida
                    mask_delete = mask_tanque & (df['data'] > dt_escolhida)
                    if mask_delete.any():
                        df = df[~mask_delete]
                                
    return df
