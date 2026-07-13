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
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "output").strip() or "output"
TELEGRAM_CHAT_FALLBACK = os.getenv("TELEGRAM_CHAT_FALLBACK", "@dicascartolaportalsimonsports").strip()

_TELEGRAM_CACHE: Optional[Dict[str, str]] = None


def _safe(value: Any, default: str = "") -> str:
    return str(default if value is None else value).strip()


def _norm(value: Any) -> str:
    return re.sub(r"\s+", " ", _safe(value)).upper()


def _materializar_credencial_google() -> str:
    cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "service_account.json").strip()
    cred_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()

    if cred_json:
        try:
            parsed = json.loads(cred_json)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"GOOGLE_SERVICE_ACCOUNT_JSON inválido: {exc}") from exc
        Path(cred_path).write_text(json.dumps(parsed, ensure_ascii=False), encoding="utf-8")

    if not cred_path or not Path(cred_path).exists():
        raise RuntimeError(
            "Credencial Google não encontrada. Defina GOOGLE_SERVICE_ACCOUNT_JSON "
            "e compartilhe a planilha com o client_email da conta de serviço."
        )
    return cred_path


def _obter_servico_sheets():
    credentials = Credentials.from_service_account_file(
        _materializar_credencial_google(),
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
    )
    return build("sheets", "v4", credentials=credentials, cache_discovery=False)


def ler_credenciais_telegram_da_planilha() -> Dict[str, str]:
    global _TELEGRAM_CACHE
    if _TELEGRAM_CACHE:
        return _TELEGRAM_CACHE
    if not PLANILHA_ID:
        raise RuntimeError("PLANILHA_ID não definido.")
    if not ABA_TELEGRAM:
        raise RuntimeError("ABA_TELEGRAM não definida.")

    response = (
        _obter_servico_sheets()
        .spreadsheets()
        .values()
        .get(spreadsheetId=PLANILHA_ID, range=f"'{ABA_TELEGRAM}'!A:D")
        .execute()
    )
    rows = response.get("values", [])
    if len(rows) < 2:
        raise RuntimeError(f"Aba '{ABA_TELEGRAM}' vazia ou sem dados suficientes.")

    headers = [_norm(value) for value in rows[0]]
    required = ("REDE", "CONTA", "CHAVE", "VALOR")
    try:
        indexes = {name: headers.index(name) for name in required}
    except ValueError as exc:
        raise RuntimeError(
            f"Aba '{ABA_TELEGRAM}' deve conter: Rede | Conta | Chave | Valor"
        ) from exc

    found: Dict[str, str] = {}
    for row in rows[1:]:
        def column(name: str) -> str:
            index = indexes[name]
            return _safe(row[index]) if index < len(row) else ""

        if _norm(column("REDE")) != "TELEGRAM":
            continue
        if CONTA_TELEGRAM and _norm(column("CONTA")) != _norm(CONTA_TELEGRAM):
            continue
        key = _norm(column("CHAVE"))
        if key:
            found[key] = column("VALOR")

    token = found.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = found.get("TELEGRAM_CHAT_ID", "").strip()
    if not token:
        raise RuntimeError(
            f"TELEGRAM_BOT_TOKEN não encontrado na aba '{ABA_TELEGRAM}' para '{CONTA_TELEGRAM}'."
        )
    if not chat_id:
        raise RuntimeError(
            f"TELEGRAM_CHAT_ID não encontrado na aba '{ABA_TELEGRAM}' para '{CONTA_TELEGRAM}'."
        )

    _TELEGRAM_CACHE = {"bot_token": token, "chat_id": chat_id, "origem": "planilha"}
    print(f"Credenciais lidas da aba '{ABA_TELEGRAM}' para '{CONTA_TELEGRAM}'.")
    return _TELEGRAM_CACHE


def obter_bot_token_chat_id() -> Tuple[str, str]:
    direct_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    direct_chat = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if direct_token and direct_chat:
        return direct_token, direct_chat
    credentials = ler_credenciais_telegram_da_planilha()
    return credentials["bot_token"], credentials["chat_id"]


def _destinos(chat_id: str) -> List[str]:
    values: List[str] = []
    for value in (chat_id, TELEGRAM_CHAT_FALLBACK):
        value = _safe(value)
        if value and value not in values:
            values.append(value)
    return values


def _telegram_url(token: str, method: str) -> str:
    return f"https://api.telegram.org/bot{token}/{method}"


def _telegram_error(response: requests.Response) -> str:
    try:
        data = response.json()
        return _safe(data.get("description") or data)
    except Exception:
        return response.text[:1200]


def validar_bot_e_destino(token: str, chat_id: str) -> str:
    response = requests.get(_telegram_url(token, "getMe"), timeout=30)
    if not response.ok or not response.json().get("ok"):
        raise RuntimeError(
            f"Token Telegram inválido: HTTP {response.status_code}: {_telegram_error(response)}"
        )
    bot = response.json().get("result", {})
    print(f"Bot autenticado: @{bot.get('username', 'desconhecido')}")

    errors: List[str] = []
    for destination in _destinos(chat_id):
        response = requests.get(
            _telegram_url(token, "getChat"), params={"chat_id": destination}, timeout=30
        )
        if response.ok and response.json().get("ok"):
            chat = response.json().get("result", {})
            print(
                f"Destino validado: {destination} "
                f"({chat.get('title') or chat.get('username') or 'chat'})"
            )
            return destination
        errors.append(
            f"{destination}: HTTP {response.status_code}: {_telegram_error(response)}"
        )
    raise RuntimeError("Nenhum destino Telegram válido. " + " | ".join(errors))


def enviar_foto(path: str, caption: str = "", parse_mode: str = "HTML") -> Dict[str, Any]:
    token, configured_chat = obter_bot_token_chat_id()
    errors: List[str] = []

    for destination in _destinos(configured_chat):
        data: Dict[str, Any] = {"chat_id": destination, "caption": caption[:1024]}
        if parse_mode:
            data["parse_mode"] = parse_mode

        with Path(path).open("rb") as file_object:
            response = requests.post(
                _telegram_url(token, "sendPhoto"),
                data=data,
                files={"photo": (Path(path).name, file_object, "image/png")},
                timeout=120,
            )

        if response.ok and response.json().get("ok"):
            print(f"Imagem enviada: {Path(path).name} → {destination}")
            return response.json()

        description = _telegram_error(response)
        if parse_mode and response.status_code == 400 and "parse" in description.lower():
            data.pop("parse_mode", None)
            with Path(path).open("rb") as file_object:
                response = requests.post(
                    _telegram_url(token, "sendPhoto"),
                    data=data,
                    files={"photo": (Path(path).name, file_object, "image/png")},
                    timeout=120,
                )
            if response.ok and response.json().get("ok"):
                print(f"Imagem enviada sem parse_mode: {Path(path).name} → {destination}")
                return response.json()
            description = _telegram_error(response)

        errors.append(f"{destination}: HTTP {response.status_code}: {description}")

    raise RuntimeError(f"Falha ao enviar '{Path(path).name}': " + " | ".join(errors))


def enviar_album(paths: List[str], caption: str = "", parse_mode: str = "HTML") -> List[Dict[str, Any]]:
    """Envia de 2 a 10 imagens agrupadas, com legenda só na primeira."""
    if not paths:
        return []
    if len(paths) == 1:
        return [enviar_foto(paths[0], caption, parse_mode)]
    if len(paths) > 10:
        responses: List[Dict[str, Any]] = []
        first = True
        for start in range(0, len(paths), 10):
            chunk = paths[start:start + 10]
            responses.extend(enviar_album(chunk, caption if first else "", parse_mode))
            first = False
        return responses

    token, configured_chat = obter_bot_token_chat_id()
    errors: List[str] = []

    for destination in _destinos(configured_chat):
        files: Dict[str, Any] = {}
        media: List[Dict[str, Any]] = []
        open_files = []
        try:
            for index, path in enumerate(paths):
                file_object = Path(path).open("rb")
                open_files.append(file_object)
                attach_name = f"photo{index}"
                files[attach_name] = (Path(path).name, file_object, "image/png")
                item: Dict[str, Any] = {
                    "type": "photo",
                    "media": f"attach://{attach_name}",
                }
                if index == 0 and caption:
                    item["caption"] = caption[:1024]
                    if parse_mode:
                        item["parse_mode"] = parse_mode
                media.append(item)

            response = requests.post(
                _telegram_url(token, "sendMediaGroup"),
                data={
                    "chat_id": destination,
                    "media": json.dumps(media, ensure_ascii=False),
                },
                files=files,
                timeout=180,
            )
        finally:
            for file_object in open_files:
                file_object.close()

        if response.ok and response.json().get("ok"):
            print(f"Álbum enviado: {len(paths)} imagens → {destination}")
            return response.json().get("result", [])

        errors.append(
            f"{destination}: HTTP {response.status_code}: {_telegram_error(response)}"
        )

    raise RuntimeError("Falha ao enviar álbum: " + " | ".join(errors))


def carregar_payload(path: Optional[str] = None) -> Dict[str, Any]:
    raw = os.getenv("PAYLOAD_JSON", "").strip()
    payload_path = Path(path or PAYLOAD_FILE)
    if not raw:
        if not payload_path.exists():
            raise RuntimeError(f"Payload não encontrado: {payload_path}")
        raw = payload_path.read_text(encoding="utf-8").strip()
    if not raw or raw == "null":
        raise RuntimeError("Payload vazio ou nulo.")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Payload JSON inválido: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("Payload precisa ser um objeto JSON.")
    return payload


def extrair_dados_publicacao(payload_root: Dict[str, Any]) -> Dict[str, Any]:
    inner = payload_root.get("payload")
    if isinstance(inner, dict):
        data = dict(inner)
        for key in (
            "tipo_publicacao",
            "rodada",
            "origem",
            "ambiente",
            "gerado_em",
            "payload_hash",
        ):
            if key not in data and key in payload_root:
                data[key] = payload_root[key]
        return data
    return dict(payload_root)


def _lower_mapping(value: Any) -> Any:
    if isinstance(value, dict):
        return {_safe(key).lower(): _lower_mapping(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_lower_mapping(item) for item in value]
    return value


def normalizar_dados_renderizacao(raw_data: Dict[str, Any]) -> Dict[str, Any]:
    """Aceita contratos novos e arquivos históricos com campos maiúsculos."""
    data = _lower_mapping(raw_data)
    if not isinstance(data, dict):
        return raw_data

    entries = data.get("dados")
    if isinstance(entries, list) and entries:
        entries = [item for item in entries if isinstance(item, dict)]
        players = any("pos" in item and "nome" in item for item in entries)
        matches = any(
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

        if players and not any(
            data.get(key) for key in ("lista", "jogadores", "time", "escalacao")
        ):
            starters = [
                item
                for item in entries
                if _safe(item.get("status"), "TITULAR").upper() != "RESERVA"
            ]
            data["jogadores"] = starters or entries
        elif matches and not any(
            data.get(key) for key in ("partidas", "jogos", "resultados")
        ):
            data["partidas"] = entries

    if not data.get("tipo_publicacao") and data.get("tipo"):
        data["tipo_publicacao"] = data["tipo"]
    return data


def _caption(rendered: RenderOutput, data: Dict[str, Any]) -> str:
    title = html.escape(rendered.title.title())
    rodada = _safe(data.get("rodada"))
    lines = [f"<b>{title}</b>"]
    if rodada and rodada not in rendered.title:
        lines.append(f"Rodada {html.escape(rodada)}")
    lines.extend(["", "📡 Portal SimonSports", "🔗 @dicascartolaportalsimonsports"])
    return "\n".join(lines)[:1024]


def _manifest_path() -> Path:
    return Path(OUTPUT_DIR, "ultima_publicacao.json")


def _save_manifest(publications: List[Dict[str, Any]]) -> None:
    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
    _manifest_path().write_text(
        json.dumps(
            {
                "gerado_em": datetime.now(timezone.utc).isoformat(),
                "publicacoes": publications,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def publicar_dados(
    raw_data: Dict[str, Any],
    *,
    payload_root: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    data = normalizar_dados_renderizacao(raw_data)
    rendered = render_publication(data, output_dir=OUTPUT_DIR)
    if not rendered.files:
        raise RuntimeError("O renderizador não produziu imagens.")

    caption = _caption(rendered, data)
    if len(rendered.files) == 1:
        enviar_foto(rendered.files[0], caption)
    else:
        enviar_album(rendered.files, caption)

    print(f"Publicação concluída: tipo={rendered.kind}; imagens={len(rendered.files)}")
    return {
        "tipo_detectado": rendered.kind,
        "tipo_publicacao": data.get("tipo_publicacao") or (payload_root or {}).get("tipo_publicacao"),
        "rodada": data.get("rodada") or (payload_root or {}).get("rodada"),
        "arquivos": rendered.files,
        "titulo": rendered.title,
    }


def _embedded_publications(payload_root: Dict[str, Any]) -> List[Dict[str, Any]]:
    publications: List[Dict[str, Any]] = []
    for container in (
        payload_root,
        payload_root.get("payload") if isinstance(payload_root.get("payload"), dict) else {},
    ):
        for key in ("publicacoes", "publicações"):
            values = container.get(key)
            if isinstance(values, list):
                publications.extend(value for value in values if isinstance(value, dict))
    return publications


def executar_publicacao() -> List[Dict[str, Any]]:
    payload_root = carregar_payload()
    token, chat_id = obter_bot_token_chat_id()
    validar_bot_e_destino(token, chat_id)

    primary = extrair_dados_publicacao(payload_root)
    queue = [primary] + _embedded_publications(payload_root)

    results: List[Dict[str, Any]] = []
    seen = set()
    for item in queue:
        normalized = normalizar_dados_renderizacao(item)
        fingerprint = (
            _safe(normalized.get("tipo_publicacao")),
            _safe(normalized.get("rodada")),
            _safe(normalized.get("titulo")),
        )
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        results.append(publicar_dados(normalized, payload_root=payload_root))

    _save_manifest(results)
    print(f"Fluxo completo: {len(results)} publicação(ões).")
    return results


if __name__ == "__main__":
    executar_publicacao()
