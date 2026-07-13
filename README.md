# cartola-engine

Motor de geração e publicação profissional do Portal SimonSports para o Telegram.

## Fluxo

1. O Apps Script envia o payload por `repository_dispatch`.
2. O GitHub Actions valida o JSON recebido.
3. O Python identifica o tipo da publicação.
4. O renderizador gera artes em PNG no diretório `output/`.
5. O token e o destino do Telegram são lidos da planilha de credenciais.
6. As imagens são publicadas no canal e gravadas no repositório.

## Tipos visuais

- `top5`: três páginas profissionais, com duas posições por página.
- `time`, `time_economico`, `time_intermediario`, `time_pontuacao`: campinho com formação, jogadores, preços, patrimônio, técnico e capitão.
- `resultados`, `resultados_live`, `placar`, `partidas`: cards paginados com mandante, visitante, placar, status e data/hora.
- Outros tipos: boletim visual profissional como fallback.

## Arquivos principais

- `app/render_telegram_cards.py`: motor gráfico.
- `app/gerar_resultados_telegram.py`: leitura da planilha, validação do bot, renderização e publicação.
- `.github/workflows/gerar.yml`: Times e Top 5.
- `.github/workflows/gerar.resultados.yml`: Resultados Live.

## Repository secrets

- `PLANILHA_ID`
- `GOOGLE_SERVICE_ACCOUNT_JSON`
- `ABA_TELEGRAM`
- `CONTA_TELEGRAM`

A planilha deve conter as chaves `TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID` na conta configurada. O bot correspondente ao token precisa ser administrador do canal e ter permissão para publicar mensagens.

## Saídas

Cada execução gera:

- uma ou mais imagens PNG em `output/`;
- `output/ultima_publicacao.json`, com tipo detectado, rodada e arquivos publicados.
