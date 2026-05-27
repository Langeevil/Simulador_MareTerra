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

## 3. Estação do Lote

A estação é definida pelo mês da `Dt.últ Biometria` do lote.

| Meses | Estação |
| --- | --- |
| Novembro a maio | Verão (`V`) |
| Junho a outubro | Inverno (`I`) |

A estação é avaliada dia a dia. Quando o peixe passa por meses de diferentes estações dentro do mesmo ciclo, a seleção da curva acompanha a sazonalidade corrente. O mesmo tanque pode fazer uso da curva de inverno para seu crescimento nos meses frios e, em seguida, fazer uso da curva de verão durante os meses de verão.

## 4. Seleção da Curva

A cada dia simulado, o código verifica a estação correspondente à data. Com a estação definida, ele localiza o dia equivalente de ciclo:

```text
dia_ciclo = linha da curva da estação do lote cujo PM está mais próximo do peso médio do plantel
```

Depois disso, a cada dia simulado o `dia_ciclo` é incrementado em `1`.

Se a estação do lote for inverno, o simulador usa:

- `Dia Inverno`;
- `PM Inverno`;
- `%PV Inverno`;
- `%mortalidade Inverno`;
- `GDP Inverno`;
- `Marco de Gestao Inverno`.

Se a estação do lote for verão, usa o conjunto equivalente de verão.

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
GDP Acumulado = Peso médio do dia - Peso médio inicial
```

### Consumo de Ração Diário

```text
Consumo Diário (kg) = Biomassa do dia * taxa PV
```

A taxa PV vem da curva da estação do lote.

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

## 10. Saída

O arquivo final é salvo como CSV com:

- separador `;`;
- codificação `utf-8-sig`;
- números em formato brasileiro;
- uma linha da última biometria;
- uma linha da data do relatório;
- linhas futuras diárias até o encerramento do lote.

Exemplo de execução:

```powershell
python .\simulador_aquicola.py --input-dir . --output simulacao_completa_br.csv --data-relatorio 26/05/2026
```
