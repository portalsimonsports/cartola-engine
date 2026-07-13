"""Executor seguro para publicação no Telegram.

Mantém a leitura das credenciais na planilha. Se o TELEGRAM_CHAT_ID
numérico cadastrado não for reconhecido pelo Telegram, usa o username
público do canal Portal SimonSports como destino alternativo.
"""

import os
import sys
from pathlib import Path

# Permite importar o módulo principal quando executado a partir da raiz.
APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import gerar_resultados_telegram as telegram  # noqa: E402


CHAT_USERNAME_PADRAO = "@dicascartolaportalsimonsports"
_obter_original = telegram.obter_bot_token_chat_id


def obter_bot_token_chat_id_com_fallback():
    bot_token, chat_id = _obter_original()
    chat_id = str(chat_id or "").strip()

    # Pode ser sobrescrito futuramente por secret/variável do workflow.
    fallback = os.getenv("TELEGRAM_CHAT_FALLBACK", CHAT_USERNAME_PADRAO).strip()

    # O ID numérico atualmente cadastrado retorna "chat not found".
    # Para canais públicos, o Bot API também aceita @username.
    if chat_id == "-1001910194081" and fallback:
        print(
            "AVISO: TELEGRAM_CHAT_ID numérico conhecido como inválido; "
            f"usando destino alternativo {fallback}."
        )
        chat_id = fallback

    return bot_token, chat_id


telegram.obter_bot_token_chat_id = obter_bot_token_chat_id_com_fallback


if __name__ == "__main__":
    telegram.executar_publicacao()
