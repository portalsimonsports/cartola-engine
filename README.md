# cartola-engine

Motor de geração e publicação profissional do Portal SimonSports para o Telegram.

## Automação

O uso normal é automático:

1. O Apps Script envia um `repository_dispatch` para cada publicação oficial.
2. O workflow correspondente inicia sem intervenção manual.
3. O GitHub Actions valida o JSON recebido.
4. O Python identifica se o payload é Econômico, Pontuação, Intermediário, Top 5 ou Resultados.
5. O renderizador gera a arte profissional diretamente com os dados enviados pelo GS.
6. O token e o destino do Telegram são lidos da planilha de credenciais.
7. As imagens são publicadas e gravadas em `output/`.

O botão **Run workflow** permanece apenas para teste, reprocessamento ou emergência.

## Fonte oficial dos times

Os times atuais não são lidos dos antigos arquivos `data/times_atual_*.json`.

A fonte oficial é o payload enviado pelo `jobTelegramDispatcher`, que contém:

- `atletas` titulares e reservas;
- `modelo` e `nome_modelo`;
- `meta.esquema`;
- `meta.custo_total`;
- capitão;
- rodada;
- mensagem e status da publicação.

Cada disparo é arquivado em `data/publicacoes_atuais/`, separado por tipo e rodada, para auditoria e reprocessamento.

## Tipos visuais

- `top5`: uma única imagem vertical de alta resolução, com GOL, LAT, ZAG, MEI, ATA e TEC.
- `time_economico`: campinho do Time Econômico.
- `time_intermediario`: campinho do Time Intermediário.
- `time_pontuacao`: campinho do Time para Pontuar.
- `resultados`, `resultados_live`, `placar`, `partidas`: cards de partidas com mandante, visitante, placar, status e data/hora.
- Outros tipos: boletim visual profissional como fallback.

Quando uma publicação gerar mais de uma imagem, o Telegram recebe um **álbum (`sendMediaGroup`)**, com a legenda somente na primeira imagem. Assim, não existe texto solto entre as páginas.

## Funcionamento de Times e Top 5

O GS envia normalmente quatro eventos independentes da mesma rodada:

1. Time Econômico;
2. Time para Pontuar;
3. Time Intermediário;
4. Top 5.

Cada execução usa exclusivamente o próprio payload recebido. Dessa forma, os campinhos refletem exatamente a rodada e os atletas que já eram publicados em texto pelo Telegram.

## Arquivos principais

- `app/render_telegram_cards.py`: motor gráfico.
- `app/gerar_resultados_telegram.py`: credenciais, normalização, álbuns e publicação.
- `app/publicar_times_top5_automatico.py`: tratamento dos payloads oficiais de Times e Top 5.
- `.github/workflows/gerar.yml`: Times e Top 5.
- `.github/workflows/gerar.resultados.yml`: Resultados Live.

## Repository secrets

- `PLANILHA_ID`
- `GOOGLE_SERVICE_ACCOUNT_JSON`
- `ABA_TELEGRAM`
- `CONTA_TELEGRAM`

A planilha deve conter `TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID`. O bot correspondente ao token precisa ser administrador do canal e ter permissão para publicar mensagens.

## Saídas

Cada execução gera:

- uma ou mais imagens PNG em `output/`;
- o payload normalizado em `data/publicacoes_atuais/`;
- `output/ultima_publicacao.json`, com todas as publicações, rodadas e arquivos enviados.
