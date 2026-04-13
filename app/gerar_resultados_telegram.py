import os
import re
import json
import requests
from typing import Dict, Optional, Tuple

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build


PLANILHA_ID = os.getenv("PLANILHA_ID", "").strip()
ABA_TELEGRAM = os.getenv("ABA_TELEGRAM", "Telegram_Cartola").strip()
CONTA_TELEGRAM = os.getenv("CONTA_TELEGRAM", "DICAS CARTOLA PORTAL SIMONSPORTS").strip()

_TELEGRAM_CACHE: Optional[Dict[str, str]] = None


def _norm(s) -> str:
    return re.sub(r"\s+", " ", str(s or "").strip()).upper()


def _obter_coluna(row, idx: int) -> str:
    return str(row[idx]).strip() if idx < len(row) else ""


def _obter_servico_sheets():
    cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "service_account.json").strip()
    if not cred_path or not os.path.exists(cred_path):
        raise RuntimeError(f"Credencial Google não encontrada: {cred_path}")

    scopes = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
    creds = Credentials.from_service_account_file(cred_path, scopes=scopes)
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


def ler_credenciais_telegram_da_planilha(
    planilha_id: Optional[str] = None,
    aba_nome: Optional[str] = None,
    conta_alvo: Optional[str] = None,
) -> Dict[str, str]:
    global _TELEGRAM_CACHE

    if _TELEGRAM_CACHE:
        return _TELEGRAM_CACHE

    planilha_id = (planilha_id or PLANILHA_ID).strip()
    aba_nome = (aba_nome or ABA_TELEGRAM).strip()
    conta_alvo = (conta_alvo or CONTA_TELEGRAM).strip()

    if not planilha_id:
        raise RuntimeError("PLANILHA_ID não definido para leitura das credenciais do Telegram.")

    service = _obter_servico_sheets()
    intervalo = f"'{aba_nome}'!A:D"

    resp = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=planilha_id, range=intervalo)
        .execute()
    )

    valores = resp.get("values", [])
    if not valores or len(valores) < 2:
        raise RuntimeError(f"Aba '{aba_nome}' vazia ou sem dados suficientes.")

    cab = [_norm(x) for x in valores[0]]

    try:
        idx_rede = cab.index("REDE")
        idx_conta = cab.index("CONTA")
        idx_chave = cab.index("CHAVE")
        idx_valor = cab.index("VALOR")
    except ValueError:
        raise RuntimeError(
            f"Aba '{aba_nome}' deve conter cabeçalhos: Rede | Conta | Chave | Valor"
        )

    encontrados: Dict[str, str] = {}

    for row in valores[1:]:
        rede = _obter_coluna(row, idx_rede)
        conta = _obter_coluna(row, idx_conta)
        chave = _obter_coluna(row, idx_chave)
        valor = _obter_coluna(row, idx_valor)

        if _norm(rede) != "TELEGRAM":
            continue
        if conta_alvo and _norm(conta) != _norm(conta_alvo):
            continue
        if not chave:
            continue

        encontrados[_norm(chave)] = valor.strip()

    bot_token = encontrados.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = encontrados.get("TELEGRAM_CHAT_ID", "").strip()

    if not bot_token:
        raise RuntimeError(
            f"TELEGRAM_BOT_TOKEN não encontrado na aba '{aba_nome}' para a conta '{conta_alvo}'."
        )
    if not chat_id:
        raise RuntimeError(
            f"TELEGRAM_CHAT_ID não encontrado na aba '{aba_nome}' para a conta '{conta_alvo}'."
        )

    _TELEGRAM_CACHE = {
        "bot_token": bot_token,
        "chat_id": chat_id,
        "aba": aba_nome,
        "conta": conta_alvo,
    }
    return _TELEGRAM_CACHE


def obter_bot_token_chat_id() -> Tuple[str, str]:
    cfg = ler_credenciais_telegram_da_planilha()
    return cfg["bot_token"], cfg["chat_id"]


def enviar_telegram_texto(
    texto: str,
    parse_mode: Optional[str] = "HTML",
    disable_web_page_preview: bool = True,
    timeout: int = 60,
) -> dict:
    bot_token, chat_id = obter_bot_token_chat_id()

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": texto,
        "disable_web_page_preview": disable_web_page_preview,
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode

    resp = requests.post(url, json=payload, timeout=timeout)
    resp.raise_for_status()

    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram sendMessage falhou: {data}")

    return data


def enviar_telegram_foto(
    caminho_imagem: str,
    legenda: str = "",
    parse_mode: Optional[str] = "HTML",
    timeout: int = 120,
) -> dict:
    bot_token, chat_id = obter_bot_token_chat_id()

    if not os.path.exists(caminho_imagem):
        raise FileNotFoundError(f"Imagem não encontrada: {caminho_imagem}")

    url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"

    data = {
        "chat_id": chat_id,
        "caption": legenda or "",
    }
    if parse_mode:
        data["parse_mode"] = parse_mode

    with open(caminho_imagem, "rb") as f:
        files = {"photo": f}
        resp = requests.post(url, data=data, files=files, timeout=timeout)

    resp.raise_for_status()

    payload = resp.json()
    if not payload.get("ok"):
        raise RuntimeError(f"Telegram sendPhoto falhou: {payload}")

    return payload