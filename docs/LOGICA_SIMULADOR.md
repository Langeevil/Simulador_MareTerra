# Lógica do Simulador Aquícola

Este documento descreve a lógica atual do `simulador_aquicola.py`: como os dados são lidos, como a estação é definida, como a curva é aplicada, quais cálculos são usados e como os marcadores de status aparecem no relatório.

## 1. Entradas do Sistema

O simulador usa quatro arquivos CSV:

| Arquivo | Finalidade |
| --- | --- |
| `plantel.csv` | Define os lotes ativos, com produtor, tanque, quantidade, peso médio e data da última biometria. |
| `tanques.csv` | Complementa informações cadastrais dos tanques. |
| `curvas.csv` | Traz as curvas de verão e inverno: peso médio de referência, `%PV`, mortalidade, GDP e marcos de gestão. |
| `racao.csv` | Tabela de referência de ração por faixa de peso. |

Os arquivos de entrada usam separador `;` e codificação `utf-8-sig`.

## 2. Data Base do Lote

Cada lote usa a data da última biometria do `plantel.csv`, coluna `Dt.últ Biometria`, como ponto inicial da simulação.

A primeira linha gerada para cada tanque representa essa biometria real.

| Campo | Regra na primeira linha |
| --- | --- |
| `Data` | Data da última biometria. |
| `Peso Medio (g)` | Peso informado no plantel. |
| `Quantidade de Peixes` | Saldo final informado no plantel. |
| `Biomassa (kg)` | `Quantidade * Peso Medio / 1000`. |
| Consumo, TCA, GDP e mortalidade | Iniciam em zero. |

## 3. Estação Dinâmica

A estação é definida pela data simulada de cada linha, não fica travada na `Dt.últ Biometria`.

| Meses | Estação |
| --- | --- |
| Novembro a maio | Verão (`V`) |
| Junho a outubro | Inverno (`I`) |

A estação é avaliada dia a dia. Quando o peixe passa por meses de diferentes estações dentro do mesmo ciclo, a seleção da curva acompanha a sazonalidade corrente. O mesmo tanque pode fazer uso da curva de inverno para seu crescimento nos meses frios e, em seguida, fazer uso da curva de verão durante os meses quentes.

No código, `detectar_estacao` usa:

```text
Verão = meses 11, 12, 1, 2, 3, 4 e 5
Inverno = meses 6, 7, 8, 9 e 10
```

## 4. Seleção da Curva

A cada dia simulado, o código verifica a estação correspondente à data. Com a estação definida, ele localiza o dia equivalente de ciclo:

```text
dia_ciclo = linha da curva da estação atual cujo PM está mais próximo do peso médio atual do peixe
```

Depois disso, a cada dia simulado o `dia_ciclo` é incrementado em `1`.

Quando ocorre uma virada de estação no meio do ciclo, o simulador recalcula o `dia_ciclo` na nova curva buscando o peso de referência mais próximo do peso real alcançado até aquele dia. Assim, a troca de inverno para verão, ou de verão para inverno, não reinicia o crescimento e não continua usando uma posição incompatível da curva anterior.

Se a estação do dia simulado for inverno, o simulador usa:

- `Dia Inverno`;
- `PM Inverno`;
- `%PV Inverno`;
- `%mortalidade Inverno`;
- `GDP Inverno`;
- `Marco de Gestao Inverno`.

Se a estação do dia simulado for verão, usa o conjunto equivalente de verão.

## 5. Simulação Oculta até a Data do Relatório

O simulador não lista todos os dias entre a última biometria e a data de geração do relatório.

Ele calcula esses dias internamente para atualizar:

- quantidade de peixes;
- peso projetado;
- biomassa;
- consumo acumulado;
- mortalidade acumulada;
- dia equivalente da curva.

No CSV, aparecem:

1. a linha da última biometria;
2. a linha da data do relatório;
3. as linhas diárias futuras.

Diário: é o cálculo efetuado apenas com as informações do dia.

Acumulado: o primeiro dia da coluna acumulado é igual ao primeiro dia da coluna diário. O segundo dia da coluna acumulado é a soma do dia anterior da coluna acumulado + o valor da segunda linha da coluna diária. A terceira linha da coluna acumulada é a soma da segunda linha da coluna acumulada com a informação do terceiro dia da coluna diária, e assim por diante, até o último dia da simulação.

## 6. Ajuste de 16% para Peixe Pronto

Durante a simulação oculta, o código verifica se o lote atingiu o marcador `Peixe Pronto`.

Se o lote atingir `Peixe Pronto` entre a última biometria e a data do relatório, o peso exibido na data do relatório é ajustado:

```text
Peso exibido = Peso projetado real * 0,84
```

Exemplo:

```text
Peso projetado real = 1050g
Peso exibido = 1050 * 0,84 = 882g
```

A projeção futura continua a partir do peso ajustado.

## 7. Marcadores de Status

O `Status` do relatório não é uma fase contínua. Ele é um marcador pontual.

Os únicos valores válidos são:

- `Class 1`;
- `Class 2`;
- `Peixe Pronto`;
- `Realizar Biometria`;
- `Tanque Disponivel`;
- vazio.

No `curvas.csv`, cada coluna de marco deve ter apenas três eventos:

| Peso de referência | Marcador |
| --- | --- |
| PM mais próximo de `30g` | `Class 1` |
| PM mais próximo de `120g` | `Class 2` |
| PM mais próximo de `900g` | `Peixe Pronto` |

As colunas usadas são:

| Estação | Coluna |
| --- | --- |
| Verão | `Marco de Gestao Verão` |
| Inverno | `Marco de Gestao Inverno` |

Além disso, se o peso exibido no relatório for exatamente `30,00g`, o status é `Class 1`; se for `120,00g`, o status é `Class 2`; se for `900,00g` ou maior, o status é `Peixe Pronto`.

O status `Realizar Biometria` aparece nos dias de cultivo `20`, `41`, `94` e `300`, desde que não exista um marcador zootécnico mais prioritário na mesma linha.

O status `Tanque Disponivel` aparece no quinto dia após a liberação do tanque, representando o fim do vazio sanitário configurado em `5` dias.

## 8. Variáveis Principais

| Variável | Significado |
| --- | --- |
| `q` | Quantidade de peixes ativa no dia. |
| `qi` | Quantidade inicial de peixes. |
| `pi` | Peso médio inicial da última biometria. |
| `pm_real` | Peso projetado real, usado para detectar `Peixe Pronto`. |
| `pm_relatorio` | Peso exibido no relatório, podendo receber ajuste de `0,84`. |
| `bm` | Biomassa do dia em kg. |
| `bm_inicial` | Biomassa da primeira linha do lote. |
| `ca_kg` | Consumo acumulado de ração em kg. |
| `faixas_racao` | Faixas de peso e preço/kg vindas de `racao.csv`. |
| `mort_acumulada_abs` | Soma de peixes mortos desde o início da simulação. |
| `dc` | Dia equivalente da curva zootécnica. |
| `fator_regional` | Fator aplicado ao GDP e ao consumo para determinadas regiões. |
| `cluster` | Perfil tecnológico do produtor, usado para selecionar curvas específicas quando existirem. |
| `data_liberacao` | Data em que o tanque foi liberado por despesca total projetada. |

## 9. Fórmulas

### Biomassa

```text
Biomassa (kg) = Quantidade de Peixes * Peso Medio (g) / 1000
```

### Mortalidade Diária

```text
Mortalidade Diária = Quantidade ativa * (%mortalidade da curva / 100)
Quantidade nova = Quantidade ativa - Mortalidade Diária
```

### Mortalidade Acumulada

```text
Mortalidade Acumulada = Soma das mortalidades diárias
```

### GDP Diário

```text
GDP Diário = Peso médio do dia - Peso médio anterior
```

Na linha em que o ajuste `0,84` é aplicado, o GDP diário é exportado como `0` para evitar um salto artificial.

### GDP Acumulado

```text
GDP Acumulado = (Peso médio do dia - Peso médio inicial) / Dias de cultivo
```

### Consumo de Ração Diário

```text
Consumo Diário (kg) = Biomassa do dia * taxa PV
```

A taxa PV vem da curva da estação do dia simulado.

Normalização:

```text
Se PV <= 1: taxa PV = PV
Se PV > 1: taxa PV = PV / 100
```

Exemplo:

```text
PV da curva = 0,0135
Interpretação = 1,35% da biomassa
Taxa usada = 0,0135
```

Portanto:

```text
Consumo Diário = Biomassa * 0,0135
```

### Consumo Acumulado

```text
Consumo Acumulado = Soma dos consumos diários desde a última biometria
```

### Custo de Ração Diário

O custo diário é calculado depois da simulação biológica, cruzando o peso médio da linha com a tabela `racao.csv`.

```text
Preço/kg = preço da faixa em que Peso Medio (g) se encaixa
Custo de Ração Diário = Consumo Diário (kg) * Preço/kg
```

As faixas usam limite inferior inclusivo e limite superior exclusivo. Exemplo:

```text
30 <= Peso Medio (g) < 100
```

Na última faixa, o limite superior também é aceito.

### Custo de Ração Acumulado

O custo acumulado começa somente na data de solicitação do relatório (`--data-relatorio`).

```text
Se Data < data_relatorio:
    Custo de Ração Acumulado = 0

Se Data >= data_relatorio:
    Custo de Ração Acumulado =
        Custo de Ração Acumulado anterior do lote
        + Custo de Ração Diário da linha atual
```

O acumulado é controlado por lote, usando `Produtor` e `Tanque` como chave.

### TCA Diário

```text
TCA Diário = Consumo Diário / Ganho de Biomassa do Dia
```

Se o ganho de biomassa for menor ou igual a zero, a TCA diária é `0`.

### TCA Acumulado

```text
TCA Acumulado = Consumo Acumulado / Ganho de Biomassa Acumulado
```

## 10. Gestão de Tanques

O relatório preenche as colunas `Tanques Liberados` e `Tanques Disponivel` com lógica booleana:

```text
0 = não liberado / não disponível
1 = liberado / disponível
```

Quando o lote atinge `Peixe Pronto`, o simulador marca `Tanques Liberados = 1` na linha desse dia. Depois disso, são adicionadas linhas de vazio sanitário com população, peso e biomassa zerados.

No quinto dia após a liberação, o simulador marca:

```text
Tanques Disponivel = 1
Status = Tanque Disponivel
```

## 11. Relatório Gerencial da Interface

A interface Streamlit gera uma visão gerencial em abas `APT`, `ITA` e `Consolidado APT + ITA`.

As colunas mensais dessas abas começam no mês da data de geração do relatório. Por exemplo, se a data do relatório for `28/05/2026`, a primeira coluna mensal será `2026-05`.

### PO Atualizado

```text
PO Atualizado = PO preenchido manualmente na tabela da interface
```

O valor não é recalculado nem convertido para mensal nessa linha.

### Abate PO Atualizado Total Mês

```text
Abate PO Atualizado Total Mês = PO preenchido na tabela * número real de dias do mês da coluna
```

Exemplo: em uma coluna `2026-05`, o multiplicador é `31`; em `2026-06`, é `30`.

### Saldo Acumulado Atualizado / Mês

```text
Saldo Acm Atualizado / mês =
    Saldo acumulado do mês anterior
    + Previsão Disponibilidade Total do mês
    - Abate PO Atualizado Total Mês
```

Essa regra evita distorções entre meses, pois o saldo de cada mês parte do saldo acumulado anterior.

### Visualização

A tabela da tela aplica destaque visual para blocos, totais, saldos e marcos operacionais. Os gráficos usam:

```text
Eixo X = mês
Eixo Y = volume ou quantidade projetada
```

As curvas dos gráficos são montadas diretamente a partir das linhas numéricas exibidas na tabela.

As tabelas exibidas nas abas `APT`, `ITA` e `Consolidado APT + ITA` não exibem casas decimais. A base interna continua numérica para cálculo e gráfico, mas a apresentação da tabela arredonda para inteiro.

Quando a interface recebe apenas um nome de arquivo em `Arquivo de saída`, o CSV da simulação é salvo em `data/output/` e o motor adiciona data e hora ao nome final.

## 12. Clusterização de Produtores

O `plantel.csv` pode conter uma coluna opcional de cluster/perfil tecnológico, como:

- `Alta Tecnologia`;
- `Media Tecnologia`;
- `Baixa Tecnologia`.

Se a coluna não existir, o simulador usa `Media Tecnologia` como padrão, sem alterar a curva atual.

O `curvas.csv` também pode conter uma coluna opcional de cluster. Quando existirem curvas específicas para o cluster do lote, o simulador usa essas curvas. Se não existirem, usa a curva padrão da estação.

Além da seleção de curva específica, o código aplica um fator de desempenho somente quando o lote possui cluster informado:

| Cluster | Fator |
| --- | --- |
| Alta Tecnologia | `1,05` |
| Media Tecnologia | `1,00` |
| Baixa Tecnologia | `0,92` |

## 13. Transição de Plantel

O motor possui uma rotina opcional para gerar um CSV-base de nova geração de povoamento.

Quando o parâmetro `--plantel-nova-geracao-output` é informado, o simulador cria um arquivo contendo os tanques que chegaram a `Tanques Disponivel = 1`.

Esse arquivo traz:

- tanque;
- data disponível para novo povoamento;
- saldo zerado;
- peso zerado;
- região;
- classe;
- status de planejamento.

Exemplo:

```powershell
python .\src\simulador_aquicola.py --input-dir .\data\input --output simulacao_completa_br.csv --plantel-nova-geracao-output plantel_nova_geracao.csv
```

## 14. Auditoria da Planilha Base

A interface Streamlit possui uma auditoria opcional para arquivos `.xlsx`.

Ela verifica fórmulas com:

- referências quebradas `#REF!`;
- possível referência circular direta;
- fórmulas aparentemente incompletas.

Essa auditoria serve como apoio para revisão da planilha base antes de usar seus números como referência gerencial.

## 15. Saída

O arquivo final é salvo como CSV com:

- separador `;`;
- codificação `utf-8-sig`;
- números em formato brasileiro;
- data e hora de geração adicionadas ao nome do arquivo;
- uma linha da última biometria;
- uma linha da data do relatório;
- linhas futuras diárias até o encerramento do lote.

Exemplo: se o nome solicitado for `simulacao_completa_br.csv`, a saída será gravada como:

```text
simulacao_completa_br_20260528_143012.csv
```

Esse padrão evita sobrescrever relatórios anteriores e mantém um histórico local das simulações geradas.

Exemplo de execução:

```powershell
python .\simulador_aquicola.py --input-dir . --output simulacao_completa_br.csv --data-relatorio 26/05/2026
```
