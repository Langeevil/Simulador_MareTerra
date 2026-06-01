from __future__ import annotations

import importlib.util
import sys
import unittest
from datetime import date
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

APP_SPEC = importlib.util.spec_from_file_location("app_module", ROOT / "app" / "app.py")
app = importlib.util.module_from_spec(APP_SPEC)
sys.modules["app_module"] = app
APP_SPEC.loader.exec_module(app)

from simulador_aquicola import definir_status, preparar_parametros_gerenciais


class SimuladorSmokeTests(unittest.TestCase):
    def test_status_markers(self) -> None:
        self.assertEqual(definir_status(50, None, 30), "Class 1")
        self.assertEqual(definir_status(900, None, 100), "Peixe Pronto")
        self.assertEqual(definir_status(80, None, 20), "Realizar Biometria")

    def test_parametros_roundtrip(self) -> None:
        csv_bytes = (
            "tipo;mes;regiao;dias_abate;po_diario_kg;classe;produtor;volume_kg\n"
            "meta;2026-05;APT;20;1000;;;\n"
            "meta;2026-05;ITA;21;500;;;\n"
            "transferencia;2026-05;APT;;;Parceria;Prod X;2500\n"
        ).encode("utf-8-sig")
        metas, terceiros = app.parse_parametros_gerenciais(csv_bytes, date(2026, 5, 29), 2)
        self.assertEqual(metas["Mês"].tolist(), ["2026-05"])
        self.assertEqual(float(metas.loc[0, "Dias Abate APT"]), 20.0)
        self.assertEqual(float(metas.loc[0, "PO Diário APT (kg)"]), 1000.0)
        self.assertEqual(len(terceiros), 1)
        exported = app.parametros_gerenciais_to_csv(metas, terceiros)
        self.assertIn(b"transferencia", exported)

    def test_parametros_does_not_create_default_months_or_values(self) -> None:
        csv_bytes = (
            "tipo;mes;regiao;dias_abate;po_diario_kg;classe;produtor;volume_kg\n"
            "meta;2026-08;APT;;1234;;;\n"
        ).encode("utf-8-sig")
        metas, terceiros = app.parse_parametros_gerenciais(csv_bytes, date(2026, 5, 29), 12)
        self.assertEqual(metas["Mês"].tolist(), ["2026-08"])
        self.assertTrue(pd.isna(metas.loc[0, "Dias Abate APT"]))
        self.assertTrue(pd.isna(metas.loc[0, "PO Diário ITA (kg)"]))
        self.assertTrue(terceiros.empty)

    def test_parametros_backend_split_and_validation(self) -> None:
        df = pd.DataFrame({
            "tipo": ["meta", "transferencia"],
            "mes": ["2026-05", "2026-05"],
            "regiao": ["APT", "ITA"],
            "dias_abate": ["20", ""],
            "po_diario_kg": ["1000", ""],
            "classe": ["", "Parceria"],
            "produtor": ["", "Prod X"],
            "volume_kg": ["", "2500"],
        })
        parametros = preparar_parametros_gerenciais(df)
        self.assertEqual(set(parametros), {"abate", "metas", "transferencias"})
        self.assertEqual(len(parametros["abate"]), 1)
        self.assertEqual(len(parametros["metas"]), 1)
        self.assertEqual(len(parametros["transferencias"]), 1)

        with self.assertRaisesRegex(ValueError, "sem colunas obrigatorias"):
            preparar_parametros_gerenciais(df.drop(columns=["volume_kg"]))

    def test_regional_po_and_saldo(self) -> None:
        mes = "Mês"
        conteudo = "Conteúdo / Bloco"
        months = ["2026-05", "2026-06"]
        df = pd.DataFrame({
            "regiao_calc": ["APT", "APT"],
            "status": ["peixe pronto", "peixe pronto"],
            "peso_medio_g": [900.0, 910.0],
            "produtor": ["Prod A", "Prod B"],
            "tanque": ["T1", "T2"],
            "mes": months,
            "classe_calc": ["Próprio", "Próprio"],
            "biomassa_kg": [1000.0, 2000.0],
            "data": pd.to_datetime(["2026-05-15", "2026-06-15"]),
        })
        metas = pd.DataFrame({
            mes: months,
            "Dias Abate APT": [20, 10],
            "PO Diário APT (kg)": [40.0, 100.0],
            "Dias Abate ITA": [20, 10],
            "PO Diário ITA (kg)": [50.0, 60.0],
        })
        terceiros = pd.DataFrame(columns=["Região Destino", "Classe", "Produtor", mes, "Volume (kg)"])
        out = app.process_regional_data(df, "APT", metas, terceiros)
        abate = out[out[conteudo] == "Abate PO Atualizado Total Mês"].iloc[0]
        saldo = out[out[conteudo] == "Saldo Acm Atualizado / mês"].iloc[0]
        self.assertEqual(float(abate["2026-05"]), 800.0)
        self.assertEqual(float(saldo["2026-05"]), 200.0)
        self.assertEqual(float(saldo["2026-06"]), 1200.0)


if __name__ == "__main__":
    unittest.main()
