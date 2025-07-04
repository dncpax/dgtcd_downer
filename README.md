# Script para download do CDD

## Intro
Facilita o download de ficheiros do Centro de Dados da DGT, para quem não possa esperar pela API que a DGT ainda irá disponibilizar.

Neste momento, só é possível descarregar ficheiros a partir do site do [CDD](https://cdd.dgterritorio.gov.pt/), desenhando áreas de interesse até 200km², clicando em cada quadrícula para adicionar à lista de downloads, e nesta lista ainda clicar no botão de descarregar todos os ficheiros selecionados.

Para quem precisa de áreas maiores que 200km² o processo é muito moroso, e potencialmente indutor de Síndrome do túnel cárpico [^1], uma vez que por agora enquanto não há uma API para o efeito!

O script permite a descarga "automática" para áreas maiores, MAS... não faz ainda a autenticação, pelo que o user tem de obter os cookies de autenticação através da consola do browser, e fornecê-los ao script.

## Créditos
À DGT o nosso agradecimento pela iniciativa de disponibilizar todos os dados do levantamento LIDAR para o território nacional continental, de forma livre e gratuita. Uma iniciativa com um alcance enorme no exercício de cidadânia no nosso País.




## How-to

**Requisitos:**
  * O python instalado no sistema
  * conta no [CDD](https://cdd.dgterritorio.gov.pt/)

**Como correr o script em modo interativo**

1. Na linha de comandos

   ´´´bash
   python3 dgtcd_downer.py -i
   ´´´

2. Necessários os valores da bounding box em WGS84, separados por vírgulas, tipo '-8.93493538, 39.40470256, -8.91592816, 39.41428785'
   
   podes usar o plugin [Lat Lon Tools](https://plugins.qgis.org/plugins/latlontools/) do QGIS, para copiar a extensão no canvas. Lembra-te **WGS84**
  
3. Acede ao [CDD](https://cdd.dgterritorio.gov.pt/), abre o dev console do teu browser (F12);
   
   no separador Network ou Storage, consegue obter os cookies necessários para correr o script. **Necessário estares autenticado**
   
4. copia o value para o cookie 'auth_session' e coloca no _prompt_ do script
5. copia o value para o cookie 'connect.sid' e coloca no _prompt_ do script
6. Define a pasta para onde queres realizar o download, 
7. Define os segundos de espera entre cada request/download 
8. Seleciona o número da coleção (ex: 1,3 ou Enter para todas na BBox)
9. E vai tomar ☕!!

## TODO

* Possibilidade de download sem o frontend atual ✅
* Adicionar a feature essencial...barra de progresso ✅
* Autenticação no script ❌
* Possibilidade de download de uma coleção apenas, várias ou todas ✅
* Definir pastas separadas para cada coleção ✅
* Usar params de entrada para permitir scriptar em batch ✅
* Criar vrt de cada coleção descarregada ❌
* Criar um tile index das coleções descarregadas ❌
* Criar Curvas de Nível como opção do script ❌
* Fazer um micro how-to para utilização ✅ (mais ou menos feito)
* Fazer um UI 💀💀💀... hmmmm nahhh! Ou melhor no QGIS!

Com a eventual disponbilização da API, o script poderá ficar obsoleto.



[^1]: https://duckduckgo.com/?t=ftsa&q=carpal+tunnel+syndrome&ia=web
