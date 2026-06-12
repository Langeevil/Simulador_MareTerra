from pathlib import Path
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent

def process_esperado_realizado() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    # --- 1. Dados Esperados ---
    historico_path = ROOT_DIR / "data" / "input" / "simulacao_completa_historico.csv"
    if historico_path.exists():
        df_historico = pd.read_csv(historico_path, delimiter=";", encoding="utf-8-sig")
        df_esperado = df_historico[df_historico["Status"] == "Peixe Pronto"].copy()
    else:
        df_esperado = pd.DataFrame(columns=["Data", "Biomassa (kg)"])
        
    if "Data" not in df_esperado.columns:
        df_esperado["Data"] = pd.Series(dtype='datetime64[ns]')
    else:
        df_esperado["Data"] = pd.to_datetime(df_esperado["Data"], format="%d/%m/%Y", errors="coerce")
        
    if "Biomassa (kg)" in df_esperado.columns:
        df_esperado["Biomassa"] = pd.to_numeric(
            df_esperado["Biomassa (kg)"].astype(str).str.replace(".", "", regex=False).str.replace(",", ".", regex=False), 
            errors="coerce"
        ).fillna(0)
    else:
        df_esperado["Biomassa"] = pd.Series(dtype=float)
    
    # --- 2. Dados Realizados ---
    despescas_path = ROOT_DIR / "data" / "input" / "despescas.csv"
    if despescas_path.exists():
        df_realizado = pd.read_csv(despescas_path, delimiter=";", encoding="utf-8-sig")
    else:
        df_realizado = pd.DataFrame(columns=["Data Despesca", "Biomassa (kg)"])
        
    if "Data Despesca" not in df_realizado.columns:
        df_realizado["Data"] = pd.Series(dtype='datetime64[ns]')
    else:
        df_realizado["Data"] = pd.to_datetime(df_realizado["Data Despesca"], format="%d/%m/%Y", errors="coerce")
        
    if "Biomassa (kg)" not in df_realizado.columns:
        df_realizado["Biomassa Realizada"] = pd.Series(dtype=float)
    else:
        df_realizado["Biomassa Realizada"] = pd.to_numeric(
            df_realizado["Biomassa (kg)"].astype(str).str.replace(".", "", regex=False).str.replace(",", ".", regex=False), 
            errors="coerce"
        ).fillna(0)
        
    # --- 3. Agregação ---
    def _aggregate(df_e, df_r, freq):
        if df_e.empty:
            e_agg = pd.Series(dtype=float, name="Biomassa")
        else:
            e_agg = df_e.set_index("Data").resample(freq)["Biomassa"].sum()
            
        if df_r.empty:
            r_agg = pd.Series(dtype=float, name="Biomassa Realizada")
        else:
            r_agg = df_r.set_index("Data").resample(freq)["Biomassa Realizada"].sum()
            
        df_agg = pd.DataFrame({
            "Biomassa Esperada": e_agg,
            "Biomassa Realizada": r_agg
        }).fillna(0)
        
        # Filtra períodos com tudo zerado
        df_agg = df_agg[(df_agg["Biomassa Esperada"] > 0) | (df_agg["Biomassa Realizada"] > 0)]
        
        df_agg["Porcentagem (%)"] = df_agg.apply(
            lambda row: (row["Biomassa Realizada"] / row["Biomassa Esperada"]) if row["Biomassa Esperada"] > 0 else 0,
            axis=1
        )
        
        if df_agg.empty:
            df_transposed = pd.DataFrame(columns=["Métrica"])
            return df_transposed

        if freq == "D":
            df_agg.index = df_agg.index.strftime("%d/%m/%Y")
        elif freq == "W-MON":
            df_agg.index = df_agg.index.strftime("Semana %W/%Y")
        elif freq == "MS":
            df_agg.index = df_agg.index.strftime("%b/%Y").str.capitalize()
            
        df_transposed = df_agg.T
        df_transposed.reset_index(inplace=True)
        df_transposed.rename(columns={"index": "Métrica"}, inplace=True)
        
        ordem = ["Biomassa Realizada", "Biomassa Esperada", "Porcentagem (%)"]
        df_transposed["Métrica"] = pd.Categorical(df_transposed["Métrica"], categories=ordem, ordered=True)
        df_transposed = df_transposed.sort_values("Métrica").reset_index(drop=True)
        
        # Inverte a ordem das colunas de data (mais recente primeiro)
        cols = list(df_transposed.columns)
        df_transposed = df_transposed[cols[0:1] + cols[1:][::-1]]
        
        return df_transposed

    df_er_diario = _aggregate(df_esperado, df_realizado, "D")
    df_er_semanal = _aggregate(df_esperado, df_realizado, "W-MON")
    df_er_mensal = _aggregate(df_esperado, df_realizado, "MS")

    return df_er_diario, df_er_semanal, df_er_mensal
