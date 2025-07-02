# Script para download do CDD

## Intro
Facilita o download de ficheiros do Centro de Dados da DGT, para quem não possa esperar pela API que a DGT ainda irá disponibilizar.
Neste momento, só é possível descarregar ficheiros a partir do site do cdd (https://cdd.dgterritorio.gov.pt/), desenhando áreas de interesse até 200km2, clicando em cada quadrícula para adicionar à lista de downloads, e nesta lista ainda clicar no botão de descarregar todos os ficheiros selecionados.
Para quem precisa de áreas maiores que 200km2 o processo é muito moroso, por agora, enquanto não há uma API para o efeito.
O script permite a descarga automática para áreas maiores, MAS... não faz ainda a autenticação, pelo que o user tem de obter os cookies de autenticação através da consola do browser, e fornecê-los ao script.

## Créditos
À DGT o nosso agradecimento pela iniciativa de disponibilizar todos os dados do levantamento LIDAR para o território nacional continental, de forma livre e gratuita. Uma iniciativa com um alcance enorme no exercício de cidadânia no nosso País.

## TODO

* Possibilidade de download sem o frontend atual ✅
* Adicionar a feature essencial...barra de progresso ✅
* Possibilidade de download de uma coleção apenas, várias ou todas ✅
* Usar params de entrada para permitir scriptar em batch
* Criar vrt de cada coleção descarregada
* Criar um tile index das coleções descarregadas
* Criar Curvas de Nível como opção do script
* Fazer um micro how-to para utilização 💀
* Fazer um UI 💀... hmmmm nahhh! Ou melhor no QGIS!

