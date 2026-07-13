from __future__ import annotations

import html
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

from render_telegram_cards import RenderOutput, render_publication


PLANILHA_ID = os.getenv("PLANILHA_ID", "").strip()
ABA_TELEGRAM = os.getenv("ABA_TELEGRAM", "Telegram_Cartola").strip()
CONTA_TELEGRAM = os.getenv("CONTA_TELEGRAM", "DICAS CARTOLA PORTAL SIMONSPORTS").strip()
PAYLOAD_FILE = os.getenv("PAYLOAD_FILE", "data/payload_dispatch.json").strip()
TELEGRAM_CHAT_FALLBACK = os.getenv(
    "TELEGRAM_CHAT_FALLBACK", "@dicascartolaportalsimonsports"
).strip()
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "output").strip() or "output"

_TELEGRAM_CACHE: Optional[Dict[str, str]] = None


def _norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).upper()


def _safe(value: Any, default: str = "") -> str:
    return str(default if value is None else value).strip()


def _obter_coluna(row: List[Any], idx: int) -> str:
    return str(row[idx]).strip() if idx < len(row) else ""


def _materializar_credencial_google() -> str:
    cred_path = os.getenv(
        "GOOGLE_APPLICATION_CREDENTIALS", "service_account.json"
    ).strip()
    cred_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()

    if cred_json:
        try:
            parsed = json.loads(cred_json)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"GOOGLE_SERVICE_ACCOUNT_JSON inválido: {exc}") from exc
        Path(cred_path).write_text(
            json.dumps(parsed, ensure_ascii=False), encoding="utf-8"
        )

    if not cred_path or not Path(cred_path).exists():
        raise RuntimeError(
            "Credencial Google não encontrada. Defina GOOGLE_SERVICE_ACCOUNT_JSON "
            "nos Repository secrets e compartilhe a planilha com o client_email."
        )
    return cred_path


def _obter_servico_sheets():
    cred_path = _materializar_credencial_google()
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
        raise RuntimeError("PLANILHA_ID não definido.")
    if not aba_nome:
        raise RuntimeError("ABA_TELEGRAM não definida.")

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
            f"Aba '{aba_nome}' deve conter: Rede | Conta | Chave | Valor"
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
        if chave:
            encontrados[_norm(chave)] = valor.strip()

    bot_token = encontrados.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = encontrados.get("TELEGRAM_CHAT_ID", "").strip()
    if not bot_token:
        raise RuntimeError(
            f"TELEGRAM_BOT_TOKEN não encontrado na aba '{aba_nome}' "
            f"para a conta '{conta_alvo}'."
        )
    if not chat_id:
        raise RuntimeError(
            f"TELEGRAM_CHAT_ID não encontrado na aba '{aba_nome}' "
            f"para a conta '{conta_alvo}'."
        )

    _TELEGRAM_CACHE = {
        "bot_token": bot_token,
        "chat_id": chat_id,
        "aba": aba_nome,
        "conta": conta_alvo,
        "origem": "planilha",
    }
    print(
        f"Credenciais do Telegram carregadas da aba '{aba_nome}' "
        f"para a conta '{conta_alvo}'."
    )
    return _TELEGRAM_CACHE


def obter_bot_token_chat_id() -> Tuple[str, str]:
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if bot_token and chat_id:
        return bot_token, chat_id
    cfg = ler_credenciais_telegram_da_planilha()
    return cfg["bot_token"], cfg["chat_id"]


def _destinos_chat(chat_id: str) -> List[str]:
    destinos: List[str] = []
    for value in (chat_id, TELEGRAM_CHAT_FALLBACK):
        value = _safe(value)
        if value and value not in destinos:
            destinos.append(value)
    return destinos


def _telegram_url(token: str, method: str) -> str:
    return f"https://api.telegram.org/bot{token}/{method}"


def _telegram_error(response: requests.Response) -> str:
    try:
        data = response.json()
        return _safe(data.get("description") or data)
    except Exception:
        return response.text[:1200]


def validar_bot_e_destino(token: str, chat_id: str) -> None:
    me = requests.get(_telegram_url(token, "getMe"), timeout=30)
    if not me.ok:
        raise RuntimeError(
            f"Token do Telegram inválido: HTTP {me.status_code}: {_telegram_error(me)}"
        )
    me_data = me.json().get("result", {})
    print(f"Bot autenticado: @{me_data.get('username', 'desconhecido')}")

    errors: List[str] = []
    for destino in _destinos_chat(chat_id):
        response = requests.get(
            _telegram_url(token, "getChat"), params={"chat_id": destino}, timeout=30
        )
        if response.ok and response.json().get("ok"):
            result = response.json().get("result", {})
            print(
                "Destino validado: "
                f"{destino} ({result.get('title') or result.get('username') or 'chat'})"
            )
            return
        errors.append(f"{destino}: {_telegram_error(response)}")
    raise RuntimeError("Nenhum destino Telegram válido. " + " | ".join(errors))


def enviar_texto(
    texto: str,
    *,
    parse_mode: Optional[str] = "HTML",
    disable_preview: bool = True,
    timeout: int = 60,
) -> Dict[str, Any]:
    token, chat_id = obter_bot_token_chat_id()
    errors: List[str] = []
    for destino in _destinos_chat(chat_id):
        payload: Dict[str, Any] = {
            "chat_id": destino,
            "text": texto,
            "disable_web_page_preview": disable_preview,
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode
        response = requests.post(
            _telegram_url(token, "sendMessage"), json=payload, timeout=timeout
        )
        if response.ok and response.json().get("ok"):
            print(f"Texto enviado ao destino {destino}.")
            return response.json()
        description = _telegram_error(response)
        if parse_mode and response.status_code == 400 and "parse" in description.lower():
            payload.pop("parse_mode", None)
            response = requests.post(
                _telegram_url(token, "sendMessage"), json=payload, timeout=timeout
            )
            if response.ok and response.json().get("ok"):
                print(f"Texto enviado sem parse_mode ao destino {destino}.")
                return response.json()
            description = _telegram_error(response)
        errors.append(f"{destino}: HTTP {response.status_code}: {description}")
    raise RuntimeError("Falha ao enviar texto: " + " | ".join(errors))


def enviar_foto(
    caminho: str,
    *,
    legenda: str = "",
    parse_mode: Optional[str] = "HTML",
    timeout: int = 120,
) -> Dict[str, Any]:
    path = Path(caminho)
    if not path.exists():
        raise FileNotFoundError(f"Imagem não encontrada: {caminho}")

    token, chat_id = obter_bot_token_chat_id()
    errors: List[str] = []
    for destino in _destinos_chat(chat_id):
        data: Dict[str, Any] = {"chat_id": destino, "caption": legenda[:1024]}
        if parse_mode:
            data["parse_mode"] = parse_mode
        with path.open("rb") as file_obj:
            response = requests.post(
                _telegram_url(token, "sendPhoto"),
                data=data,
                files={"photo": (path.name, file_obj, "image/png")},
                timeout=timeout,
            )
        if response.ok and response.json().get("ok"):
            print(f"Imagem '{path.name}' enviada ao destino {destino}.")
            return response.json()
        description = _telegram_error(response)
        if parse_mode and response.status_code == 400 and "parse" in description.lower():
            data.pop("parse_mode", None)
            with path.open("rb") as file_obj:
                response = requests.post(
                    _telegram_url(token, "sendPhoto"),
                    data=data,
                    files={"photo": (path.name, file_obj, "image/png")},
                    timeout=timeout,
                )
            if response.ok and response.json().get("ok"):
                print(f"Imagem '{path.name}' enviada sem parse_mode a {destino}.")
                return response.json()
            description = _telegram_error(response)
        errors.append(f"{destino}: HTTP {response.status_code}: {description}")
    raise RuntimeError(f"Falha ao enviar imagem '{path.name}': " + " | ".join(errors))


def carregar_payload() -> Dict[str, Any]:
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


def extrair_dados_publicacao(payload_raiz: Dict[str, Any]) -> Dict[str, Any]:
    interno = payload_raiz.get("payload")
    if isinstance(interno, dict):
        dados = dict(interno)
        for chave in (
            "tipo_publicacao",
            "rodada",
            "origem",
            "ambiente",
            "gerado_em",
            "payload_hash",
        ):
            if chave not in dados and chave in payload_raiz:
                dados[chave] = payload_raiz[chave]
        return dados
    return dict(payload_raiz)


def _lower_mapping(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key).strip().lower(): _lower_mapping(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_lower_mapping(item) for item in value]
    return value


def normalizar_dados_renderizacao(dados: Dict[str, Any]) -> Dict[str, Any]:
    """Converte bases antigas em maiúsculas para o contrato visual atual."""
    normalized = _lower_mapping(dados)
    if not isinstance(normalized, dict):
        return dados

    raw_data = normalized.get("dados")
    if isinstance(raw_data, list) and raw_data:
        entries = [item for item in raw_data if isinstance(item, dict)]
        player_like = any("pos" in item and "nome" in item for item in entries)
        match_like = any(
            any(
                key in item
                for key in (
                    "mandante",
                    "visitante",
                    "home",
                    "away",
                    "time_casa",
                    "time_fora",
                )
            )
            for item in entries
        )
        if player_like and not any(
            normalized.get(key)
            for key in ("lista", "jogadores", "time", "escalacao")
        ):
            starters = [
                item
                for item in entries
                if _safe(item.get("status"), "TITULAR").upper() != "RESERVA"
            ]
            normalized["jogadores"] = starters or entries
        elif match_like and not any(
            normalized.get(key)
            for key in ("partidas", "jogos", "resultados")
        ):
            normalized["partidas"] = entries

    if "tipo_publicacao" not in normalized and normalized.get("tipo"):
        normalized["tipo_publicacao"] = normalized.get("tipo")
    return normalized


def _caption(rendered: RenderOutput, dados: Dict[str, Any]) -> str:
    rodada = _safe(dados.get("rodada"))
    title = html.escape(rendered.title.title())
    lines = [f"<b>{title}</b>"]
    if rodada and rodada not in rendered.title:
        lines.append(f"Rodada {html.escape(rodada)}")
    lines.extend(
        [
            "",
            "📊 Conteúdo visual gerado automaticamente",
            "📡 Portal SimonSports",
            "🔗 @dicascartolaportalsimonsports",
        ]
    )
    return "\n".join(lines)[:1024]


def _gravar_manifesto(
    payload_raiz: Dict[str, Any], dados: Dict[str, Any], rendered: RenderOutput
) -> None:
    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
    manifest = {
        "gerado_em": datetime.now(timezone.utc).isoformat(),
        "tipo_detectado": rendered.kind,
        "tipo_publicacao": dados.get("tipo_publicacao")
        or payload_raiz.get("tipo_publicacao"),
        "rodada": dados.get("rodada") or payload_raiz.get("rodada"),
        "arquivos": rendered.files,
        "titulo": rendered.title,
    }
    Path(OUTPUT_DIR, "ultima_publicacao.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def executar_publicacao() -> None:
    payload_raiz = carregar_payload()
    dados = normalizar_dados_renderizacao(extrair_dados_publicacao(payload_raiz))
    tipo = _safe(
        dados.get("tipo_publicacao")
        or payload_raiz.get("tipo_publicacao")
        or "telegram"
    )
    rodada = _safe(dados.get("rodada") or payload_raiz.get("rodada"))
    print(f"Publicação recebida: tipo={tipo!r}, rodada={rodada!r}")

    token, chat_id = obter_bot_token_chat_id()
    validar_bot_e_destino(token, chat_id)

    rendered = render_publication(dados, output_dir=OUTPUT_DIR)
    if not rendered.files:
        raise RuntimeError("O renderizador não produziu nenhuma imagem.")
    print(
        f"Arte profissional gerada: tipo={rendered.kind}, "
        f"arquivos={len(rendered.files)}"
    )

    caption = _caption(rendered, dados)
    for index, file_path in enumerate(rendered.files, start=1):
        current_caption = caption if index == 1 else ""
        enviar_foto(file_path, legenda=current_caption)
        print(f"Imagem {index}/{len(rendered.files)} publicada.")

    _gravar_manifesto(payload_raiz, dados, rendered)
    print("Publicação profissional concluída com sucesso.")


if __name__ == "__main__":
    executar_publicacao()
