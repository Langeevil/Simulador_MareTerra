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

from simulador_aquicola import (
    FaixaRacao,
    adicionar_custos_racao,
    definir_status,
    preparar_parametros_gerenciais,
    resolve_runtime_path,
)


class SimuladorSmokeTests(unittest.TestCase):
    def test_status_markers(self) -> None:
        self.assertEqual(definir_status(50, None, 30), "Class 1")
        self.assertEqual(definir_status(900, None, 100), "Peixe Pronto")
        self.assertEqual(definir_status(80, None, 20), "Realizar Biometria")

    def test_default_relative_paths_resolve_from_project_root(self) -> None:
        self.assertEqual(resolve_runtime_path("data/input").resolve(), (ROOT / "data" / "input").resolve())
        self.assertEqual(
            app.resolve_output_path(r".\data\output\simulacao.csv").resolve(),
            (ROOT / "data" / "output" / "simulacao.csv").resolve(),
        )

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

    def test_parametros_decimal_dot_does_not_gain_zeroes_on_export(self) -> None:
        csv_bytes = (
            "tipo;mes;regiao;dias_abate;po_diario_kg;classe;produtor;volume_kg\n"
            "meta;2026-06;APT;20.0;90000.0;;;\n"
            "meta;2026-06;ITA;21;45.000;;;\n"
            "transferencia;2026-06;APT;;;Parceria;Prod X;2500.0\n"
        ).encode("utf-8-sig")
        metas, terceiros = app.parse_parametros_gerenciais(csv_bytes, date(2026, 6, 1), 12)
        self.assertEqual(float(metas.loc[0, "Dias Abate APT"]), 20.0)
        self.assertEqual(float(metas.loc[0, "PO Diário APT (kg)"]), 90000.0)
        self.assertEqual(float(metas.loc[0, "PO Diário ITA (kg)"]), 45000.0)

        exported = app.parametros_gerenciais_to_csv(metas, terceiros).decode("utf-8-sig")
        self.assertIn("meta;2026-06;APT;20;90000;;;", exported)
        self.assertIn("meta;2026-06;ITA;21;45000;;;", exported)
        self.assertIn("transferencia;2026-06;APT;;;Parceria;Prod X;2500", exported)
        self.assertNotIn("200", exported)
        self.assertNotIn("900000", exported)

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

    def test_terceiros_transferencias_origem_vazia_vira_terceiros(self) -> None:
        csv_bytes = (
            "Mês;Região Origem;Região Destino;Classe;Produtor;Volume (kg)\n"
            "01/06/2026;;APT;Parceria;Prod X;2500\n"
        ).encode("utf-8-sig")
        df = app.parse_terceiros_e_transferencias(csv_bytes)
        self.assertEqual(df.loc[0, "Mês"], "2026-06")
        self.assertEqual(df.loc[0, "Região Origem"], "Terceiros")

        exported = app.terceiros_e_transferencias_to_csv(df).decode("utf-8-sig")
        self.assertIn("2026-06;Terceiros;APT;Parceria;Prod X;2500", exported)

    def test_transferencias_biomassa_aplica_debito_e_credito_por_mes(self) -> None:
        base = pd.DataFrame({
            "regiao_calc": ["APT", "ITA"],
            "classe_calc": ["Próprio", "Próprio"],
            "produtor": ["Prod A", "Prod A"],
            "mes": ["2026-06", "2026-06"],
            "biomassa_kg": [1000.0, 100.0],
        })
        transferencias = pd.DataFrame({
            "Mês": ["2026-06", "2026-06"],
            "Região Origem": ["APT", ""],
            "Região Destino": ["ITA", "APT"],
            "Classe": ["Próprio", "Próprio"],
            "Produtor": ["Prod A", "Prod A"],
            "Volume (kg)": [300.0, 50.0],
        })

        resultado = app.aplicar_transferencias_biomassa(base, transferencias)
        valores = resultado.set_index(["regiao_calc", "produtor", "mes"])["biomassa_kg"]

        self.assertEqual(float(valores.loc[("APT", "Prod A", "2026-06")]), 750.0)
        self.assertEqual(float(valores.loc[("ITA", "Prod A", "2026-06")]), 400.0)

    def test_transferencia_debita_classe_real_da_origem(self) -> None:
        base = pd.DataFrame({
            "regiao_calc": ["ITA"],
            "classe_calc": ["Integração"],
            "produtor": ["Prod A"],
            "mes": ["2026-06"],
            "biomassa_kg": [350000.0],
        })
        transferencias = pd.DataFrame({
            "Mês": ["2026-06"],
            "Região Origem": ["ITA"],
            "Região Destino": ["APT"],
            "Classe": ["Parceria"],
            "Produtor": ["Prod A"],
            "Volume (kg)": [100000.0],
        })

        resultado = app.aplicar_transferencias_biomassa(base, transferencias)
        valores = resultado.set_index(["regiao_calc", "classe_calc", "produtor", "mes"])["biomassa_kg"]

        self.assertEqual(float(valores.loc[("ITA", "Integração", "Prod A", "2026-06")]), 250000.0)
        self.assertEqual(float(valores.loc[("APT", "Parceria", "Prod A", "2026-06")]), 100000.0)

    def test_custo_acumulado_uses_report_date_and_lote_group(self) -> None:
        registros = [
            {
                "Produtor": "Prod A",
                "Tanque": "T1",
                "Data": date(2026, 6, 2),
                "Peso Medio (g)": 100.0,
                "Quantidade de Peixes": 1000,
                "Consumo de Racao Diario (kg)": 20.0,
            },
            {
                "Produtor": "Prod A",
                "Tanque": "T1",
                "Data": date(2026, 5, 31),
                "Peso Medio (g)": 100.0,
                "Quantidade de Peixes": 1000,
                "Consumo de Racao Diario (kg)": 10.0,
            },
            {
                "Produtor": "Prod A",
                "Tanque": "T2",
                "Data": date(2026, 6, 1),
                "Peso Medio (g)": 100.0,
                "Quantidade de Peixes": 1000,
                "Consumo de Racao Diario (kg)": 7.0,
            },
            {
                "Produtor": "Prod A",
                "Tanque": "T1",
                "Data": date(2026, 6, 1),
                "Peso Medio (g)": 100.0,
                "Quantidade de Peixes": 1000,
                "Consumo de Racao Diario (kg)": 5.0,
            },
        ]
        faixas = [FaixaRacao(0.0, 200.0, 2.0, "Inicial")]

        resultado = adicionar_custos_racao(registros, faixas, date(2026, 6, 1))

        self.assertEqual(
            [(row["Tanque"], row["Data"]) for row in resultado],
            [
                ("T1", date(2026, 5, 31)),
                ("T1", date(2026, 6, 1)),
                ("T1", date(2026, 6, 2)),
                ("T2", date(2026, 6, 1)),
            ],
        )
        self.assertEqual(
            [row["Custo de Racao Acumulado"] for row in resultado],
            [0.0, 10.0, 50.0, 14.0],
        )

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
