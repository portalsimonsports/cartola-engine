# cartola-engine

Motor de geração e publicação profissional do Portal SimonSports para o Telegram.

## Automação

O uso normal é automático:

1. O Apps Script envia o payload por `repository_dispatch`.
2. O workflow correspondente inicia sem intervenção manual.
3. O GitHub Actions valida o JSON recebido.
4. O Python gera as artes profissionais.
5. O token e o destino do Telegram são lidos da planilha de credenciais.
6. As imagens são publicadas e gravadas em `output/`.

O botão **Run workflow** permanece apenas para teste, reprocessamento ou emergência.

## Tipos visuais

- `top5`: uma única imagem vertical de alta resolução, com GOL, LAT, ZAG, MEI, ATA e TEC.
- `time`, `time_economico`, `time_intermediario`, `time_pontuacao`: campinho com formação, titulares, preços, patrimônio, técnico e capitão.
- `resultados`, `resultados_live`, `placar`, `partidas`: cards de partidas com mandante, visitante, placar, status e data/hora.
- Outros tipos: boletim visual profissional como fallback.

Quando uma publicação gerar mais de uma imagem, o Telegram recebe um **álbum (`sendMediaGroup`)**, com a legenda somente na primeira imagem. Assim, não existe texto solto entre as páginas.

## Pacote Times e Top 5

O workflow `.github/workflows/gerar.yml` publica:

1. o payload principal recebido;
2. publicações adicionais incluídas em `publicacoes` ou `times` no payload;
3. os arquivos `times_atual_pontuacao.json`, `times_atual_intermediario.json` e `times_atual_economico.json`, desde que sejam da mesma rodada do Top 5.

Arquivos de rodadas antigas são ignorados para impedir a publicação de times desatualizados.

## Arquivos principais

- `app/render_telegram_cards.py`: motor gráfico.
- `app/gerar_resultados_telegram.py`: credenciais, normalização, álbuns e publicação.
- `app/publicar_times_top5_automatico.py`: pacote automático de Top 5 e campinhos.
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
- `output/ultima_publicacao.json`, com todas as publicações, rodadas e arquivos enviados.
