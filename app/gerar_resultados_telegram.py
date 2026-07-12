import os
import re
import json
from pathlib import Path
from typing import Dict, Optional, Tuple, Any, List

import requests
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build


PLANILHA_ID = os.getenv("PLANILHA_ID", "").strip()
ABA_TELEGRAM = os.getenv("ABA_TELEGRAM", "Telegram_Cartola").strip()
CONTA_TELEGRAM = os.getenv("CONTA_TELEGRAM", "DICAS CARTOLA PORTAL SIMONSPORTS").strip()
PAYLOAD_FILE = os.getenv("PAYLOAD_FILE", "data/payload_dispatch.json").strip()

_TELEGRAM_CACHE: Optional[Dict[str, str]] = None


def _norm(s: Any) -> str:
    return re.sub(r"\s+", " ", str(s or "").strip()).upper()


def _obter_coluna(row: List[Any], idx: int) -> str:
    return str(row[idx]).strip() if idx < len(row) else ""


def _materializar_credencial_google() -> Optional[str]:
    """Cria o arquivo da service account a partir do secret, quando fornecido."""
    cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "service_account.json").strip()
    cred_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()

    if cred_json:
        try:
            parsed = json.loads(cred_json)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"GOOGLE_SERVICE_ACCOUNT_JSON inválido: {exc}") from exc

        Path(cred_path).write_text(
            json.dumps(parsed, ensure_ascii=False),
            encoding="utf-8",
        )

    return cred_path if cred_path and os.path.exists(cred_path) else None


def _obter_servico_sheets():
    cred_path = _materializar_credencial_google()
    if not cred_path:
        raise RuntimeError(
            "Credencial Google não encontrada. Defina GOOGLE_SERVICE_ACCOUNT_JSON "
            "ou disponibilize GOOGLE_APPLICATION_CREDENTIALS."
        )

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
    except ValueError as exc:
        raise RuntimeError(
            f"Aba '{aba_nome}' deve conter cabeçalhos: Rede | Conta | Chave | Valor"
        ) from exc

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
        "origem": "planilha",
    }
    return _TELEGRAM_CACHE


def obter_bot_token_chat_id() -> Tuple[str, str]:
    """Prioriza GitHub Secrets e usa a planilha como fallback."""
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()

    if bot_token and chat_id:
        return bot_token, chat_id

    cfg = ler_credenciais_telegram_da_planilha()
    return cfg["bot_token"], cfg["chat_id"]


def _telegram_post(
    metodo: str,
    *,
    json_payload: Optional[dict] = None,
    data: Optional[dict] = None,
    files: Optional[dict] = None,
    timeout: int = 60,
) -> dict:
    bot_token, _ = obter_bot_token_chat_id()
    url = f"https://api.telegram.org/bot{bot_token}/{metodo}"
    resp = requests.post(url, json=json_payload, data=data, files=files, timeout=timeout)

    if not resp.ok:
        detalhe = resp.text[:1500]
        raise RuntimeError(f"Telegram HTTP {resp.status_code}: {detalhe}")

    payload = resp.json()
    if not payload.get("ok"):
        raise RuntimeError(f"Telegram {metodo} falhou: {payload}")
    return payload


def enviar_telegram_texto(
    texto: str,
    parse_mode: Optional[str] = "Markdown",
    disable_web_page_preview: bool = True,
    timeout: int = 60,
) -> dict:
    _, chat_id = obter_bot_token_chat_id()

    payload = {
        "chat_id": chat_id,
        "text": texto,
        "disable_web_page_preview": disable_web_page_preview,
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode

    try:
        return _telegram_post("sendMessage", json_payload=payload, timeout=timeout)
    except RuntimeError as exc:
        if parse_mode and "400" in str(exc):
            payload.pop("parse_mode", None)
            return _telegram_post("sendMessage", json_payload=payload, timeout=timeout)
        raise


def enviar_telegram_foto(
    caminho_imagem: str,
    legenda: str = "",
    parse_mode: Optional[str] = "Markdown",
    timeout: int = 120,
) -> dict:
    _, chat_id = obter_bot_token_chat_id()

    if not os.path.exists(caminho_imagem):
        raise FileNotFoundError(f"Imagem não encontrada: {caminho_imagem}")

    data = {"chat_id": chat_id, "caption": legenda or ""}
    if parse_mode:
        data["parse_mode"] = parse_mode

    with open(caminho_imagem, "rb") as arquivo:
        files = {"photo": arquivo}
        try:
            return _telegram_post("sendPhoto", data=data, files=files, timeout=timeout)
        except RuntimeError as exc:
            if parse_mode and "400" in str(exc):
                arquivo.seek(0)
                data.pop("parse_mode", None)
                return _telegram_post("sendPhoto", data=data, files=files, timeout=timeout)
            raise


def carregar_payload() -> dict:
    """Lê PAYLOAD_JSON ou PAYLOAD_FILE e devolve um objeto normalizado."""
    raw = os.getenv("PAYLOAD_JSON", "").strip()

    if not raw:
        path = Path(PAYLOAD_FILE)
        if not path.exists():
            raise RuntimeError(f"Payload não encontrado: {PAYLOAD_FILE}")
        raw = path.read_text(encoding="utf-8").strip()

    if not raw or raw == "null":
        raise RuntimeError("Payload vazio ou nulo.")

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Payload JSON inválido: {exc}") from exc

    if not isinstance(payload, dict):
        raise RuntimeError("Payload precisa ser um objeto JSON.")

    return payload


def extrair_dados_publicacao(payload_raiz: dict) -> dict:
    """Aceita tanto o envelope completo quanto o conteúdo interno em payload."""
    interno = payload_raiz.get("payload")
    if isinstance(interno, dict):
        dados = dict(interno)
        for chave in ("tipo_publicacao", "rodada", "origem", "ambiente"):
            if chave not in dados and chave in payload_raiz:
                dados[chave] = payload_raiz[chave]
        return dados
    return payload_raiz


def extrair_mensagem(dados: dict) -> str:
    for chave in ("mensagem_oficial", "mensagem", "texto", "message", "caption"):
        valor = dados.get(chave)
        if isinstance(valor, str) and valor.strip():
            return valor.strip()
    raise RuntimeError(
        "Nenhuma mensagem encontrada no payload. Esperado: mensagem_oficial, mensagem, texto, message ou caption."
    )


def dividir_mensagem(texto: str, limite: int = 4000) -> List[str]:
    """Divide sem exceder o limite de 4096 caracteres do sendMessage."""
    texto = texto.strip()
    if len(texto) <= limite:
        return [texto]

    partes: List[str] = []
    restante = texto
    while len(restante) > limite:
        corte = restante.rfind("\n", 0, limite)
        if corte < limite // 2:
            corte = restante.rfind(" ", 0, limite)
        if corte < limite // 2:
            corte = limite
        partes.append(restante[:corte].strip())
        restante = restante[corte:].strip()

    if restante:
        partes.append(restante)
    return partes


def localizar_imagem(dados: dict) -> Optional[str]:
    candidatos = [
        dados.get("caminho_imagem"),
        dados.get("imagem"),
        dados.get("arquivo_imagem"),
        dados.get("output_file"),
    ]

    for candidato in candidatos:
        if isinstance(candidato, str) and candidato.strip():
            caminho = candidato.strip()
            if os.path.exists(caminho):
                return caminho

    return None


def executar_publicacao() -> None:
    payload_raiz = carregar_payload()
    dados = extrair_dados_publicacao(payload_raiz)
    mensagem = extrair_mensagem(dados)
    imagem = localizar_imagem(dados)

    tipo = str(dados.get("tipo_publicacao") or payload_raiz.get("tipo_publicacao") or "telegram").strip()
    rodada = dados.get("rodada") or payload_raiz.get("rodada") or ""

    print(f"Publicação identificada: tipo={tipo!r}, rodada={rodada!r}")
    print(f"Tamanho da mensagem: {len(mensagem)} caracteres")

    if imagem:
        legenda = mensagem[:1000]
        enviar_telegram_foto(imagem, legenda=legenda)
        restante = mensagem[1000:].strip()
        for parte in dividir_mensagem(restante):
            if parte:
                enviar_telegram_texto(parte)
        print(f"Publicação enviada com imagem: {imagem}")
        return

    partes = dividir_mensagem(mensagem)
    for indice, parte in enumerate(partes, start=1):
        enviar_telegram_texto(parte)
        print(f"Parte {indice}/{len(partes)} enviada ao Telegram.")

    print("Publicação concluída com sucesso.")


if __name__ == "__main__":
    executar_publicacao()
