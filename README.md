# HydroSizer

Plugin QGIS para dimensionamento hidráulico auditável, trecho a trecho, de
redes de abastecimento de água. O HydroSizer utiliza vazões, comprimentos e
pressões já calculados pelo QGISRed ou disponíveis em camadas compatíveis,
testa os produtos ativos do catálogo e seleciona a menor solução admissível
segundo os critérios do projeto.

O fluxo reúne detecção do cenário, validação dos dados, catálogo de tubos,
Hazen–Williams ou Darcy–Weisbach, verificação de pressão nas extremidades,
dimensionamento em lote, revisão dos resultados, aplicação opcional e auditada
na camada e emissão da memória de cálculo em HTML com planilha CSV detalhada.

**Versão operacional:** 1.0.2  
**Compatibilidade declarada:** QGIS 3.22 a 3.99  
**Idiomas:** português do Brasil e inglês  
**Dependências externas:** nenhuma

## O que o HydroSizer faz — e o que não faz

O plugin dimensiona tubos com base em um cenário hidráulico existente. Ele não
calcula demandas, não executa o QGISRed, não redistribui vazões, não resolve
novamente a rede e não analisa transientes ou golpe de aríete. Os arquivos
QGISRed `*_Options.dbf` e `*_Materials.dbf` são sempre acessados somente para
leitura. O catálogo editável do HydroSizer é independente.

A atualização da camada de tubulações é opcional. Antes de qualquer alteração,
o plugin mostra valores atuais e propostos, solicita confirmação, produz uma
auditoria e deixa as mudanças no buffer de edição do QGIS para que o usuário
possa revisar, desfazer ou salvar.



## Dados necessários antes de começar

Abra no QGIS o projeto e o cenário que serão dimensionados. Para o fluxo
completo, devem estar disponíveis:

- camada linear de tubulações, com ID único e comprimento positivo;
- camada ou tabela de resultados dos trechos, com o mesmo ID e a vazão;
- camada pontual de resultados dos nós, com ID e pressão, quando a verificação
  de classe de pressão estiver habilitada;
- resultados correspondentes ao cenário de projeto que será documentado;
- catálogo HydroSizer com produtos ativos e dados hidráulicos verificados.

Salve o projeto QGIS antes de iniciar. Confirme as unidades do QGISRed e não
misture resultados gerados em cenários diferentes. Pontos altos, pontos baixos
e outros locais críticos devem existir como nós se suas pressões precisarem ser
consideradas.

## Tutorial completo

A interface principal é organizada em cinco etapas. Os botões **Anterior** e
**Próximo** apenas navegam: eles não calculam nem salvam dados. Abra cada
atividade dentro da etapa e siga a sequência abaixo.

### 1. Projeto

#### 1.1 Detectar o cenário hidráulico

1. Clique em **Detectar a partir do projeto atual**.
2. Confira o arquivo `*_Options.dbf` recomendado, a unidade de vazão e o método
   de perda de carga.
3. Se o arquivo correto não for encontrado, use **Escolher Options DBF**.
4. Corrija manualmente unidade ou método somente quando a detecção não
   representar o cenário carregado.

A detecção é somente leitura. Ela não abre uma simulação e não altera opções do
QGISRed.

#### 1.2 Mapear camadas e campos

1. Clique em **Atualizar camadas do projeto**.
2. Escolha a camada de tubulações e seu campo de ID.
3. Escolha o campo de comprimento da tubulação.
4. Escolha a camada ou tabela de resultados dos trechos.
5. Mapeie o ID do resultado e o campo de vazão.
6. Clique em **Armazenar mapeamento temporário**.

O relacionamento é feito pelo ID normalizado, nunca pela ordem das linhas. O
mapeamento existe apenas na sessão atual do plugin e deve ser refeito após uma
recarga.

#### 1.3 Validar os dados de entrada

Clique em **Validar mapeamento armazenado**. Corrija todos os erros antes de
dimensionar. A validação verifica, entre outros pontos:

- IDs vazios, inválidos ou duplicados;
- tubos sem resultado e resultados sem tubo;
- vazões não numéricas ou não finitas;
- comprimentos não numéricos, nulos ou negativos;
- alterações nas fontes e nos campos mapeados.

Vazões negativas são preservadas nos registros, mas o módulo é usado nos
cálculos de velocidade e perda de carga. Uma validação com situação
**APROVADO** libera uma base coerente para as etapas seguintes.

### 2. Critérios

#### 2.1 Preparar o catálogo de produtos

O catálogo é universal para o perfil QGIS e fica separado dos arquivos do
QGISRed. Na primeira execução em um perfil cujo banco esteja vazio, o
HydroSizer carrega automaticamente o catálogo inicial incluído, com 77
produtos. Um catálogo existente nunca é substituído ou complementado
automaticamente. O usuário ainda pode editar os produtos ou usar **Importar
CSV**. A importação é transacional: se uma linha for inválida, nada é
importado.

Para cada produto, informe pelo menos códigos e nomes, DN, diâmetro interno e
unidades. Complete também os campos necessários ao método e aos critérios:

- coeficiente `C` para Hazen–Williams;
- rugosidade absoluta para Darcy–Weisbach;
- pressão admissível para verificar classe de pressão;
- custo unitário e moeda para calcular custos;
- valor de material do QGISRed para aplicar o material na camada.

Use **Validar** para localizar produtos incompletos. Somente produtos ativos e
hidraulicamente completos participam do dimensionamento. Desativar um produto
significa indisponibilidade geral; não use essa ação apenas para restringir um
projeto.

Em **Produtos permitidos neste projeto**, mantenha **Todos os materiais
ativos** ou escolha um código de material. Esse filtro é temporário e não
altera o catálogo universal.

#### 2.2 Definir critérios hidráulicos e de seleção

Escolha **Hazen–Williams** ou **Darcy–Weisbach**. Depois habilite apenas os
critérios aplicáveis ao projeto:

- perda de carga unitária máxima e sua unidade;
- velocidade máxima;
- velocidade mínima desabilitada, apenas como alerta ou obrigatória;
- DN mínimo;
- estimativa inicial de Bresse;
- capacidade do produto para a pressão máxima nas extremidades.

No método Darcy–Weisbach, confira a viscosidade cinemática e a unidade. Vazão e
comprimento não são digitados nessa etapa: o lote usa automaticamente os
valores mapeados de cada trecho.

Entre os candidatos que atendem a todos os critérios obrigatórios, a seleção é
determinística: menor DN, menor custo disponível, maior pressão admissível e,
por fim, menor ID estável do catálogo. O critério controlador mostrado no
resultado indica a condição mais próxima de limitar o produto selecionado.

#### 2.3 Configurar a verificação automática de pressão

1. Escolha a camada de tubulações, a camada pontual de resultados dos nós e os
   campos de ID e pressão.
2. Informe a unidade em que a pressão está armazenada.
3. Confirme o SRC e a tolerância de coincidência entre extremidades e nós.
4. Se necessário, selecione uma margem multiplicativa ou aditiva.
5. Clique em **Atualizar camadas e catálogo** e confira o resumo.

O HydroSizer relaciona o primeiro e o último vértice de cada tubo aos pontos da
camada nodal. Para cada trecho, usa a maior pressão entre as duas extremidades,
aplica a margem configurada e rejeita produtos cuja pressão admissível seja
insuficiente. Não é necessário verificar trecho a trecho; a ferramenta
individual fica em **Ferramentas avançadas** apenas para diagnóstico.

### 3. Dimensionamento

#### 3.1 Executar o lote em memória

1. Escolha **Todos os tubos mapeados** ou **Somente feições selecionadas**.
2. Informe a unidade do atributo de comprimento mapeado.
3. Clique em **Executar dimensionamento em lote somente em memória**.
4. Aguarde o processamento ou use **Cancelar**.

Até esse ponto nenhuma camada é modificada. O resultado pode ser:

- **Dimensionado**: existe produto que atende aos critérios;
- **Dimensionado com alerta**: solução encontrada com condição informativa;
- **Sem solução**: nenhum produto ativo atende aos critérios;
- **Dados insuficientes**: faltam dados do trecho, catálogo ou pressão.

Se houver muitos trechos sem solução, revise unidades, critérios, filtro de
material e abrangência do catálogo antes de simplesmente ampliar os limites.

#### 3.2 Revisar e incluir resultados

A tabela mostra produto, vazão, comprimento, velocidade, perda de carga,
pressão na unidade do projeto, critério controlador, alertas e custo.

1. Use pesquisa e filtros de situação ou inclusão.
2. Selecione linhas e use **Incluir selecionadas** ou **Excluir selecionadas**.
3. Use **Selecionar no mapa** para conferir os trechos no QGIS.
4. Se necessário, exporte as linhas atualmente exibidas com **Exportar CSV**.

Somente linhas dimensionadas e incluídas podem ser aplicadas ou emitidas nos
documentos finais. Inclusão, exclusão e filtros modificam apenas a memória do
plugin.

### 4. Aplicar — opcional

Ignore esta etapa se quiser apenas analisar ou documentar os resultados. Para
atualizar atributos existentes na camada de tubulações:

1. Mapeie os campos de destino para material, DN, diâmetro interno,
   coeficiente `C` ou rugosidade e classe de pressão.
2. Confira as unidades dos campos de destino.
3. Escolha a pasta obrigatória de auditoria.
4. Clique em **Preparar plano antes/depois**.
5. Revise os valores mantidos e alterados.
6. Clique em **Aplicar alterações confirmadas** e confirme novamente.
7. Inspecione a tabela de atributos e o mapa.
8. Use **Salvar edições da camada** no QGIS para persistir ou **Desfazer** para
   reverter.

O plugin não cria campos. Qualquer mudança na seleção, no mapeamento ou nos
dados invalida o plano e exige nova preparação. Falhas críticas desfazem o
comando de edição. A auditoria grava CSV e JSON com valores anteriores e
propostos, critérios, versões, fontes e hash do catálogo usado.

Depois de salvar novos diâmetros, execute novamente a simulação hidráulica no
QGISRed. Retorne à etapa **Projeto**, atualize os resultados, valide e repita o
dimensionamento até que o projeto convirja. O HydroSizer não presume que uma
única passagem produza o estado hidráulico final.

### 5. Documentos

Preencha título do projeto, cliente, local, fase, cenário hidráulico,
responsável técnico, registro profissional, código, revisão e descrição da
concepção. Em seguida:

1. Clique em **Exportar memória de cálculo HTML + planilha CSV**.
2. Escolha o nome e a pasta de destino.
3. Abra o HTML no navegador e revise identificação, critérios, valores críticos,
   quantitativos e anexos.
4. Para obter PDF, use **Imprimir > Salvar como PDF** no navegador.
5. Confira o CSV detalhado e mantenha ambos os arquivos juntos.

O documento usa exatamente o retrato de dimensionamento revisado em memória.
Ele deve ser conferido e assinado pelo profissional responsável; o plugin não
substitui a responsabilidade técnica.

## Ferramentas avançadas

O botão **Ferramentas avançadas** abre recursos que não são obrigatórios no
fluxo normal:

- diagnóstico do ambiente QGIS com exportação JSON;
- conversor de unidades e cálculo demonstrativo;
- verificação de um trecho por Hazen–Williams;
- verificação de um trecho por Darcy–Weisbach;
- diagnóstico de pressão para um tubo e um produto.

Use-os para investigar unidades, catálogo ou um resultado específico, não para
substituir o processamento em lote validado.

## Solução de problemas

**O arquivo Options não foi encontrado:** salve o projeto, confirme que os
arquivos QGISRed estão acessíveis e escolha o DBF manualmente.

**A validação informa tubos sem resultado:** confirme os campos de ID e execute
novamente o cenário no QGISRed. Não relacione tabelas pela posição das linhas.

**As extremidades não encontram nós:** confira SRC, geometria da camada nodal e
tolerância. Tolerâncias excessivas podem produzir correspondências ambíguas.

**Nenhum produto é selecionado:** valide o catálogo, confira produtos ativos,
filtro de material, unidades, método, perda de carga, velocidade e pressão.

**A aplicação foi bloqueada:** os dados mudaram depois do lote ou do plano.
Valide, dimensione, revise e prepare novamente.

**A memória sai como rascunho:** complete os campos de identificação e gere os
documentos outra vez.


## Projeto, suporte e licença

- Código-fonte: <https://github.com/Evanderson-Aguiar/HydroSizer>
- Problemas e sugestões: <https://github.com/Evanderson-Aguiar/HydroSizer/issues>
- Autor: Evanderson H. Aguiar
- Contato: <evanderson.eng@gmail.com>

HydroSizer é distribuído sob a licença GNU General Public License, versão 2 ou
posterior (`GPL-2.0-or-later`). Consulte o arquivo `LICENSE`.
