# Simulador de Planejamento Aquícola

Simulador em Python para projetar o crescimento de lotes de peixes em tanques de cultivo, usando dados de plantel, tanques, curvas zootécnicas sazonais e tabela de ração.

O script principal é [`simulador_aquicola.py`](./simulador_aquicola.py).

## O que o simulador faz

O simulador processa os lotes ativos do arquivo `plantel.csv` e projeta, dia a dia, a evolução de cada tanque até que o lote atinja o peso de despesca de `900g`, fique sem peixes ativos ou alcance o limite de `730` dias simulados.

Durante a simulação, ele calcula:

- quantidade de peixes sobreviventes;
- peso médio diário;
- biomassa em kg;
- consumo de ração diário e acumulado;
- TCA diária e acumulada;
- GDP diário e acumulado;
- mortalidade diária e mortalidade acumulada;
- sobrevivência diária e acumulada;
- status do lote: `Alevinagem`, `Class 1 — Recria`, `Class 2 — Engorda` ou `Despescado`.

O desempenho é ajustado por sazonalidade:

- `Verão`: outubro a março;
- `Inverno`: abril a setembro.

## Arquivos de entrada

Por padrão, o simulador espera os seguintes arquivos CSV:

| Arquivo | Descrição |
| --- | --- |
| `tanques.csv` | Cadastro das estruturas/tanques. |
| `plantel.csv` | Inventário dos lotes ativos, com produtor, tanque, quantidade, peso médio e data da última biometria. |
| `curvas.csv` | Curvas zootécnicas de verão e inverno, com peso médio, GDP, mortalidade e taxa de arraçoamento. |
| `racao.csv` | Tabela de faixas de peso, fases produtivas, tipo de ração e preço. |

Os arquivos de entrada devem estar em `utf-8-sig` e separados por ponto e vírgula (`;`).

O script aceita os cabeçalhos usados nos arquivos de exemplo, como:

- `Saldo Final`;
- `Dt.últ Biometria`;
- `Última Pesagem(g)`;
- `Região`;
- `Dia Verão`;
- `PM Verão`;
- `%PV Verão`;
- `%mortalidade Verão`;
- `GDP Verão`;
- `Dia Inverno`;
- `PM Inverno`;
- `%PV Inverno`;
- `%mortalidade Inverno`;
- `GDP Inverno`.

## Arquivo de saída

O relatório final é salvo como CSV diário no padrão brasileiro.

Por padrão, o nome gerado é:

```text
simulacao_completa_br.csv
```

A saída usa:

- separador por ponto e vírgula (`;`),
- codificação `utf-8-sig`,
- data no formato `YYYY-MM-DD`,
- ponto como separador de milhar e vírgula como separador decimal nas colunas numéricas,
- uma linha por dia simulado de cada lote.

## Regras de cálculo

As principais métricas do relatório são calculadas assim:

| Métrica | Fórmula |
| --- | --- |
| Consumo de Ração Diário | `Biomassa do dia (kg) * (%PV da curva / 100)` |
| Consumo de Ração Acumulado | Soma do consumo diário desde o início da simulação do lote. |
| Mortalidade Diária | `Quantidade ativa no início do dia * (%mortalidade da curva / 100)` |
| Mortalidade Acumulada (%) | `Mortos acumulados / quantidade inicial * 100` |
| GDP Diário | `Peso médio do dia - peso médio do dia anterior` |
| GDP Acumulado | `Peso médio do dia - peso médio inicial` |
| TCA Diário | `Consumo diário / ganho de biomassa do dia` |
| TCA Acumulado | `Consumo acumulado / ganho de biomassa acumulado` |

Quando o ganho de biomassa é menor ou igual a zero, a TCA correspondente é exportada como `0`.

## Como utilizar

Coloque os arquivos `tanques.csv`, `plantel.csv`, `curvas.csv` e `racao.csv` na mesma pasta do script e execute:

```powershell
python .\simulador_aquicola.py
```

Para usar os arquivos na área de trabalho e salvar o resultado também lá:

```powershell
python .\simulador_aquicola.py --input-dir "C:\Users\gabriel\Desktop" --output "C:\Users\gabriel\Desktop\simulacao_completa_br.csv"
```

Para exibir mensagens sobre lotes ignorados por erro de dados:

```powershell
python .\simulador_aquicola.py --input-dir "C:\Users\gabriel\Desktop" --mostrar-erros
```

## Parâmetros disponíveis

| Parâmetro | Padrão | Uso |
| --- | --- | --- |
| `--input-dir` | `.` | Pasta onde estão os CSVs de entrada. |
| `--tanques` | `tanques.csv` | Nome do arquivo de tanques. |
| `--plantel` | `plantel.csv` | Nome do arquivo de plantel. |
| `--curvas` | `curvas.csv` | Nome do arquivo de curvas zootécnicas. |
| `--racao` | `racao.csv` | Nome do arquivo de ração. |
| `--output` | `simulacao_completa_br.csv` | Caminho ou nome do arquivo final. |
| `--mostrar-erros` | desativado | Mostra inconsistências encontradas em lotes individuais. |

## Requisitos

O simulador usa apenas a biblioteca padrão do Python. Não é necessário instalar Pandas, NumPy ou outras dependências.

Recomendado:

```text
Python 3.10+
```

## Observações

Lotes com quantidade menor ou igual a zero, peso médio inválido, peso médio igual ou maior que `900g`, ou datas inválidas são ignorados. Com `--mostrar-erros`, o script informa quais linhas foram descartadas por inconsistência.
