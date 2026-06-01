# Simulador de Planejamento Aquícola

Simulador em Python para projetar o crescimento de lotes de peixes em tanques de cultivo, usando dados de plantel, tanques, curvas zootécnicas sazonais e tabela de ração.

O script principal é [`src/simulador_aquicola.py`](./src/simulador_aquicola.py).

A interface gráfica em Streamlit fica em [`app/app.py`](./app/app.py).

## O que o simulador faz

O simulador processa os lotes ativos do arquivo `plantel.csv` e projeta, dia a dia, a evolução de cada tanque até que o lote atinja o peso de despesca de `900g`, fique sem peixes ativos ou alcance o limite de `730` dias simulados.

Durante a simulação, ele calcula:

- quantidade de peixes sobreviventes;
- peso médio diário;
- biomassa em kg;
- consumo de ração diário e acumulado;
- custo de ração diário e acumulado;
- TCA diária e acumulada;
- GDP diário e acumulado;
- mortalidade diária e mortalidade acumulada;
- sobrevivência diária e acumulada;
- marcadores de status: `Class 1`, `Class 2`, `Peixe Pronto`, `Realizar Biometria` e `Tanque Disponivel`;
- liberação e disponibilidade de tanques após vazio sanitário de 5 dias.

O desempenho é ajustado por sazonalidade:

- `Verão`: novembro a maio;
- `Inverno`: junho a outubro.

A estação é avaliada pela data de cada dia simulado. Se o lote atravessar uma virada de estação, o simulador recalcula o dia equivalente na nova curva usando o peso atual do peixe.

## Arquivos de entrada

Por padrão, o simulador espera os seguintes arquivos CSV:

| Arquivo | Descrição |
| --- | --- |
| `tanques.csv` | Cadastro das estruturas/tanques. |
| `plantel.csv` | Inventário dos lotes ativos, com produtor, tanque, quantidade, peso médio e data da última biometria. |
| `curvas.csv` | Curvas zootécnicas de verão e inverno, com peso médio, GDP, mortalidade e taxa de arraçoamento. |
| `racao.csv` | Tabela de faixas de peso, fases produtivas, tipo de ração e preço. |
| `parametros_gerenciais.csv` | Obrigatório. Metas de PO, dias de abate e transferências usadas pela interface. |

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
simulacao_completa_br_aaaammdd_hhmmss.csv
```

O simulador sempre adiciona data e hora ao nome informado em `--output`. Assim, uma nova execução não substitui o relatório anterior e o diretório mantém um histórico dos arquivos gerados.

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
| Consumo de Ração Diário | `Biomassa do dia (kg) * taxa PV normalizada` |
| Consumo de Ração Acumulado | Soma do consumo diário desde o início da simulação do lote. |
| Custo de Ração Diário | `Consumo de ração diário (kg) * Preço/kg da faixa de peso em racao.csv` |
| Custo de Ração Acumulado | Soma dos custos diários por lote a partir da data do relatório. Antes dessa data, fica `0`. |
| Mortalidade Diária | `Quantidade ativa no início do dia * (%mortalidade da curva / 100)` |
| Mortalidade Acumulada (peixes) | Soma simples dos mortos diários desde o início do lote. |
| GDP Diário | `Peso médio do dia - peso médio do dia anterior` |
| GDP Acumulado | `(Peso médio do dia - peso médio inicial) / dias de cultivo` |
| TCA Diário | `Consumo diário / ganho de biomassa do dia` |
| TCA Acumulado | `Consumo acumulado / ganho de biomassa acumulado` |

Quando o ganho de biomassa é menor ou igual a zero, a TCA correspondente é exportada como `0`.

Observação sobre `%PV`: nos arquivos atuais, valores como `0,0135` já representam `1,35%` da biomassa. Por isso, o simulador usa o valor diretamente quando ele é menor ou igual a `1`. Se algum arquivo vier com `1,35`, o código interpreta como percentual e divide por `100`.

## Como utilizar

Os arquivos de entrada ficam em `data/input/`. Para executar pela linha de comando:

```powershell
python .\src\simulador_aquicola.py --input-dir .\data\input --output "D:\mareterra\simulador\data\output\simulacao_completa_br.csv"
```

Para usar os arquivos na área de trabalho e salvar o resultado também lá:

```powershell
python .\src\simulador_aquicola.py --input-dir "C:\Users\gabriel\Desktop" --output "C:\Users\gabriel\Desktop\simulacao_completa_br.csv"
```

Para exibir mensagens sobre lotes ignorados por erro de dados:

```powershell
python .\src\simulador_aquicola.py --input-dir "C:\Users\gabriel\Desktop" --mostrar-erros
```

Para abrir a interface gráfica:

```powershell
pip install -r requirements.txt
streamlit run .\app\app.py
```

A interface também gera um relatório gerencial em Excel com abas `APT`, `ITA` e `Consolidado APT + ITA`, além de uma auditoria opcional de fórmulas para planilhas `.xlsx`.

Na tabela gerencial da interface:

- As colunas mensais vêm dos meses preenchidos no `parametros_gerenciais.csv`.
- O arquivo obrigatório `parametros_gerenciais.csv` preenche as tabelas editáveis; sem ele, a execução fica bloqueada.
- A interface não cria metas, dias de abate ou meses padrão quando o arquivo não traz esses valores.
- A tela permite baixar o `parametros_gerenciais.csv` atualizado e, no modo local, salva esse arquivo na pasta de entrada escolhida.
- O seletor `Meses exibidos no relatório da tela` filtra dinamicamente tabelas e gráficos.
- `PO Atualizado` usa exatamente o valor informado em `PO Diário APT (kg)` ou `PO Diário ITA (kg)`.
- `Abate PO Atualizado Total Mês` é calculado por `PO Diário * Dias Abate`, usando os valores preenchidos na tabela gerencial.
- `Saldo Acm Atualizado / mês` acumula `Saldo Atualizado / dia * Dias de Abate` somado ao saldo acumulado do mês anterior.
- As tabelas exibidas na tela usam destaque visual para blocos, totais, saldos e marcos de gestão, sem casas decimais.
- Os gráficos usam o eixo X como mês e o eixo Y como volume projetado, com curvas ligadas diretamente às linhas numéricas da tabela.
- Quando o nome de saída não contém pasta, a interface salva o CSV em `data/output/` com data e hora no nome.
- A aba `Consolidado APT + ITA` usa o layout operacional com blocos `APT`, `ITAPORÃ`, `Geral por dia` e `Geral por mês`.
- Quando o `curvas.csv` possui coluna de cluster/perfil, a interface exibe um comparativo opcional de programas/curvas empilhadas sem substituir os dados da simulação.

Formato do `parametros_gerenciais.csv`:

```csv
tipo;mes;regiao;dias_abate;po_diario_kg;classe;produtor;volume_kg
meta;2026-05;APT;21;90000;;;
meta;2026-05;ITA;21;45000;;;
transferencia;2026-05;APT;;;Parceria;Produtor X;2500
```

Para gerar um pacote executável local no Windows:

```powershell
.\build_exe.ps1
```

O script valida a estrutura, instala dependências, compila os arquivos Python, limpa builds antigos e gera o pacote com PyInstaller.

O arquivo será criado em:

```text
SimuladorBiomassa.exe
```

Ao abrir pelo executável, uma pequena janela de controle fica na barra de tarefas do Windows. Use o botão `Encerrar` nessa janela para finalizar o servidor local do Streamlit. Fechar apenas a aba do navegador não encerra o app.

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
| `--plantel-nova-geracao-output` | vazio | Gera um CSV opcional com tanques disponíveis para novo povoamento. |

## Requisitos

O simulador de linha de comando usa apenas a biblioteca padrão do Python. A interface gráfica usa Streamlit.

Recomendado:

```text
Python 3.10+
```

## Observações

Lotes com quantidade menor ou igual a zero, peso médio inválido, peso médio igual ou maior que `900g`, ou datas inválidas são ignorados. Com `--mostrar-erros`, o script informa quais linhas foram descartadas por inconsistência.
