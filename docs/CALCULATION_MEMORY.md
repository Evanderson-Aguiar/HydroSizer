# Memória de cálculo hidráulico

A Etapa 15 emite uma memória de cálculo do empreendimento em HTML e uma
planilha detalhada em CSV. Os documentos usam o retrato revisado do
dimensionamento em memória e não alteram projeto, camadas nem catálogo.
Desde a Etapa 17, o HTML acompanha automaticamente o idioma do QGIS em pt_BR
ou inglês. Textos livres informados pelo usuário não são traduzidos.

## Estrutura do documento

O HTML apresenta:

1. capa, identificação do empreendimento e controle do documento;
2. objeto e delimitação do escopo calculado;
3. cenário hidráulico e unidades adotadas;
4. critérios de dimensionamento e formulação hidráulica;
5. síntese com total de trechos, extensão e custo;
6. valores críticos, incluindo as menores e maiores pressões nas
   extremidades, e quantitativos por material e diâmetro;
7. anexos de dimensionamento por trecho e rastreabilidade computacional.

O Anexo A.1 reúne grandezas hidráulicas, material e diâmetros. O Anexo A.2
identifica os nós inicial e final e mostra as pressões na unidade adotada no
cálculo do projeto. O Anexo B registra somente a ferramenta e as versões do
HydroSizer, QGIS e QGISRed.

Quando for necessário um PDF, abra o HTML em um navegador e use **Imprimir >
Salvar como PDF**. Esse fluxo preserva melhor o layout e evita manter um
renderizador PDF diferente da memória aprovada.

## Escopo e rastreabilidade

A memória consolida o dimensionamento trecho a trecho usando as vazões já
existentes no resultado hidráulico. Ela não calcula demandas, não redistribui
vazões e não resolve novamente a rede.

O CSV mantém os cabeçalhos técnicos estabelecidos em português para
compatibilidade e usa codificação UTF-8 com BOM. Ele preserva
valores originais, conversões SI, produto selecionado, resultados hidráulicos,
nós, pressões, custos, decisão e observações de cada trecho.
