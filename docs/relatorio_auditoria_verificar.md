# Relatorio de Auditoria - verificar.txt

Data da auditoria: 03/06/2026

Escopo: validacao estatica dos requisitos listados em `verificar.txt`, cruzando regras matematicas, fluxo Streamlit, estilos visuais e artefatos locais. Itens marcados como "Nao rola" foram ignorados.

## Resumo Executivo

- Validado: 24 itens
- Incompleto: 5 itens
- Quebrado: 2 itens
- Ausente: 2 itens

Verificacoes executadas:

- `python -m py_compile app\app.py app\theme_config.py app\theme_consolidado.py src\simulador_aquicola.py math\calculos_saldo.py launcher.py`: passou.
- `python -m unittest discover -s tests -v`: passou com 8 testes.
- `python -m pytest -q`: nao executado porque `pytest` nao esta instalado no ambiente.

## Checklist de Auditoria

- [ ] **Consumo de Racao Acumulado (kg)**

  Status: Incompleto

  Localizacao: `src/simulador_aquicola.py:1016`, `src/simulador_aquicola.py:650`

  Analise/Problema: A soma diaria por tanque existe e usa a biomassa com peixes vivos do dia, mas a fase nutricional e aplicada depois para custo/classificacao. A coluna `Qtd Racao Und`/fase da curva e lida, mas nao e usada no consumo diario.

- [x] **TCA Acumulado**

  Status: Validado

  Localizacao: `src/simulador_aquicola.py:1020`

  Analise/Problema: A formula esta implementada como `ca_kg / ganho_bm_total`, com protecao para ganho menor ou igual a zero.

- [x] **Mortalidade Acumulada (peixes)**

  Status: Validado

  Localizacao: `src/simulador_aquicola.py:1004`

  Analise/Problema: O decaimento diario usa a populacao ativa `q`, subtrai os mortos do dia e acumula em `mort_acumulada_abs`.

- [x] **PO Atualizado**

  Status: Validado

  Localizacao: `app/app.py:532`, `app/app.py:561`

  Analise/Problema: Usa diretamente `PO Diario {regiao} (kg)` vindo da tabela gerencial, sem recalculo na linha `PO Atualizado`.

- [ ] **Biometria na Coluna Status**

  Status: Ausente

  Localizacao: `src/simulador_aquicola.py:823`

  Analise/Problema: O status usa dias fixos `{20, 41, 94, 300}` como `"Realizar Biometria"`. Nao ha gatilho para marcar automaticamente `"Biometria"` no dia da `Dt.ult Biometria` do `plantel.csv`.

- [ ] **Regras para Tanques Disponiveis**

  Status: Quebrado

  Localizacao: `src/simulador_aquicola.py:1092`

  Analise/Problema: O codigo adiciona uma nova linha no quinto dia do vazio sanitario com `Tanques Disponivel = 1`. O requisito pede preencher, na mesma linha da liberacao, a data `data_liberado + 5 dias`.

- [ ] **Conferencia da Planilha de Projecao**

  Status: Incompleto

  Localizacao: `app/app.py:1039`, `app/app.py:1248`

  Analise/Problema: Existe auditoria opcional para CSV, verificando `#REF!`, referencia circular direta e formulas incompletas. Nao ha auditoria completa de planilha Excel/base nem validacao automatica ampla.

- [x] **Melhorar a Apresentacao Geral do App**

  Status: Validado

  Localizacao: `app/app.py:135`, `app/app.py:1381`

  Analise/Problema: As abas APT, ITA e Consolidado existem; ha CSS visual aplicado. A sidebar esta apenas colapsada e nao ha uso de `st.sidebar`.

- [x] **Gerar o Executavel**

  Status: Validado

  Localizacao: `build_exe.ps1:1`

  Analise/Problema: O script PyInstaller existe e o arquivo `SimuladorBiomassa.exe` esta presente na raiz do projeto.

- [ ] **Testar o Executavel**

  Status: Ausente

  Localizacao: Nao encontrado

  Analise/Problema: Nao ha evidencia de testes em diferentes computadores. Foram encontrados apenas o artefato e logs locais.

- [x] **Arredondamento Geral**

  Status: Validado

  Localizacao: `src/simulador_aquicola.py:1168`, `app/app.py:799`

  Analise/Problema: Contagens, mortalidade, flags e visualizacao gerencial sao formatadas sem casas decimais.

- [x] **Abate PO Atualizado Total Mes**

  Status: Validado

  Localizacao: `app/app.py:532`

  Analise/Problema: Calcula `PO Diario * Dias Abate`. Observacao: usa os dias preenchidos na tabela, nao os dias calendario reais do mes.

- [ ] **Saldo Acumulado Atualizado / Mes**

  Status: Incompleto

  Localizacao: `math/calculos_saldo.py:11`, `app/app.py:716`

  Analise/Problema: O calculo regional esta correto por `cumsum`, mas o consolidado usa apenas os dias de abate da APT para o grupo geral.

- [x] **Tabela Interativa na Tela do Aplicativo**

  Status: Validado

  Localizacao: `app/app.py:1120`, `app/app.py:1136`

  Analise/Problema: `st.data_editor` permite editar metas PO, dias de abate e transferencias.

- [x] **Disponibilidade de Edicao a Qualquer Momento**

  Status: Validado

  Localizacao: `app/app.py:1494`, `app/app.py:1604`

  Analise/Problema: Os inputs sao renderizados antes da simulacao e continuam disponiveis depois que o relatorio e gerado.

- [x] **Preencher Coluna Tanques Liberados**

  Status: Validado

  Localizacao: `src/simulador_aquicola.py:1043`

  Analise/Problema: Marca `Tanques Liberados = 1` no primeiro dia em que o status e `"Peixe Pronto"`.

- [x] **Aba de Informacoes Conjuntas (APT e ITA)**

  Status: Validado

  Localizacao: `app/app.py:581`, `app/app.py:1381`

  Analise/Problema: A aba consolidada soma e organiza os dados de APT e ITA.

- [x] **Terceira Aba do Relatorio (Consolidado APT + ITA)**

  Status: Validado

  Localizacao: `app/app.py:1381`

  Analise/Problema: A terceira aba renderiza consolidado com tabela, metricas e grafico.

- [x] **Selecao de Meses na Tela**

  Status: Validado

  Localizacao: `app/app.py:1151`, `app/app.py:1346`

  Analise/Problema: `st.multiselect` filtra metas, terceiros, tabelas e graficos.

- [ ] **Legenda no Lado Esquerdo do Grafico**

  Status: Quebrado

  Localizacao: `app/app.py:897`

  Analise/Problema: A legenda esta configurada como `orient="bottom"`, nao no lado esquerdo.

- [x] **GDP Acumulado (g)**

  Status: Validado

  Localizacao: `src/simulador_aquicola.py:1032`

  Analise/Problema: A formula e `(pm_relatorio - pi) / dias_cultivo`.

- [x] **Arquivo parametros_gerenciais.csv**

  Status: Validado

  Localizacao: `src/simulador_aquicola.py:207`, `app/app.py:56`

  Analise/Problema: O quinto arquivo obrigatorio esta integrado com suporte a metas, abate e transferencias.

- [x] **Botao para Salvar parametros_gerenciais.csv**

  Status: Validado

  Localizacao: `app/app.py:1170`

  Analise/Problema: O botao salva `parametros_csv` no caminho local e atualiza o estado da sessao.

- [x] **Programas Empilhados**

  Status: Validado

  Localizacao: `app/app.py:1310`

  Analise/Problema: O comparativo de curvas por cluster e exibido em tabela empilhada.

- [x] **Diferenciacao de Cores por Tipo de Quadro**

  Status: Validado

  Localizacao: `app/theme_config.py:191`

  Analise/Problema: Os padroes A/B/C aplicam cores por secao Proprio, Integracao e Parceria.

- [x] **Visibilidade do Nome do Quadro (Coluna A)**

  Status: Validado

  Localizacao: `app/theme_config.py:310`, `app/app.py:819`

  Analise/Problema: Largura e quebra de texto estao configuradas para a coluna de rotulo.

- [x] **Pintar a Linha Dias de Abate**

  Status: Validado

  Localizacao: `app/theme_consolidado.py:28`, `app/app.py:942`

  Analise/Problema: A linha recebe destaque especifico.

- [x] **Diferenciar Previsao Disponibilidade Total de Abate PO Atualizado Total Mes**

  Status: Validado

  Localizacao: `app/app.py:922`

  Analise/Problema: Ha estilos distintos para as duas linhas.

- [x] **Alternancia de Cores nas Linhas das Fazendas**

  Status: Validado

  Localizacao: `app/theme_config.py:279`

  Analise/Problema: O zebrado por linhas de corpo esta implementado.

- [ ] **Pintar o Cabecalho com Cor Diferente**

  Status: Incompleto

  Localizacao: `app/theme_config.py:321`, `app/theme_consolidado.py:280`

  Analise/Problema: No fluxo usado pelas abas, o cabecalho `th` fica transparente/cinza. O cabecalho verde existe apenas no fallback `styled_report_dataframe`.

- [x] **Correcao das Informacoes do Grafico**

  Status: Validado

  Localizacao: `app/app.py:857`, `app/app.py:876`

  Analise/Problema: Os graficos sao gerados a partir das linhas numericas da tabela filtrada, com eixos X/Y explicitos.

- [x] **Colorizacao Geral de Linhas e Visualizacao**

  Status: Validado

  Localizacao: `app/theme_config.py:232`, `app/theme_consolidado.py:172`

  Analise/Problema: Estilos por bloco, totais, saldos, marcos e alternancia estao presentes e sao chamados no `st.dataframe`.

- [x] **Persistencia Bidirecional**

  Status: Validado

  Localizacao: `app/app.py:1190`, `app/app.py:1228`

  Analise/Problema: O app salva no CSV e recarrega alteracoes externas no modo local por watcher de `mtime`.

