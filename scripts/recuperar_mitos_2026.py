import csv
import json
import time
from pathlib import Path

import requests

# Coleta histórica 2026 - execução pontual
MITOS = {
    1: 24137264, 2: 46095320, 3: 24807770, 4: 48921295,
    5: 28933900, 6: 45564289, 7: 17950024, 8: 2275569,
    9: 361314, 10: 13356680, 11: 44851575, 12: 5461035,
    13: 14013757, 14: 9533445, 15: 51001311, 16: 2425397,
    17: 45146407, 18: 51030023, 19: 44621481, 20: 49149324,
    21: 14650635, 22: 19572648, 23: 50198965, 24: 44759774,
}

BASES = [
    "https://api.cartolafc.globo.com/time/id/{time_id}/{rodada}",
    "https://api.cartola.globo.com/time/id/{time_id}/{rodada}",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; SimonSportsCartola/1.0)",
    "Accept": "application/json,text/plain,*/*",
}


def buscar(rodada, time_id):
    erros = []
    for tpl in BASES:
        url = tpl.format(time_id=time_id, rodada=rodada)
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            if r.ok:
                return {"ok": True, "url": url, "data": r.json()}
            erros.append(f"{url} -> HTTP {r.status_code}: {r.text[:160]}")
        except Exception as e:
            erros.append(f"{url} -> {type(e).__name__}: {e}")
        time.sleep(0.5)
    return {"ok": False, "erros": erros}


def normalizar(rodada, time_id, res, gerado_em):
    data = res["data"]
    time_obj = data.get("time") or {}
    nome_time = time_obj.get("nome", "")
    capitao_id = data.get("capitao_id")
    esquema_id = data.get("esquema_id")
    patrimonio = data.get("patrimonio")
    valor_time = data.get("valor_time")
    mito_pontos = data.get("pontos")
    mito_pontos_campeonato = data.get("pontos_campeonato")
    fonte = res.get("url", "")

    rows = []
    for a in data.get("atletas") or []:
        aid = a.get("atleta_id")
        rows.append({
            "ANO": 2026,
            "RODADA": rodada,
            "MITO_TIME_ID": time_id,
            "MITO_NOME_TIME": nome_time,
            "MITO_PONTOS": mito_pontos,
            "MITO_PONTOS_CAMPEONATO": mito_pontos_campeonato,
            "ATLETA_ID": aid,
            "APELIDO": a.get("apelido", ""),
            "NOME": a.get("nome", ""),
            "POSICAO_ID": a.get("posicao_id"),
            "CLUBE_ID": a.get("clube_id"),
            "PRECO": a.get("preco_num"),
            "PONTOS_ATLETA": a.get("pontos_num"),
            "SCOUTS": json.dumps(a.get("scout") or {}, ensure_ascii=False, separators=(",", ":")),
            "CAPITAO": "SIM" if aid == capitao_id else "NAO",
            "RESERVA": "NAO",
            "TECNICO": "SIM" if a.get("posicao_id") == 6 else "NAO",
            "ESQUEMA_ID": esquema_id,
            "PATRIMONIO": patrimonio,
            "VALOR_TIME": valor_time,
            "FONTE": fonte,
            "CAPTURADO_EM": gerado_em,
            "RAW_JSON_ATLETA": json.dumps(a, ensure_ascii=False, separators=(",", ":")),
        })

    for a in data.get("reservas") or []:
        aid = a.get("atleta_id")
        rows.append({
            "ANO": 2026,
            "RODADA": rodada,
            "MITO_TIME_ID": time_id,
            "MITO_NOME_TIME": nome_time,
            "MITO_PONTOS": mito_pontos,
            "MITO_PONTOS_CAMPEONATO": mito_pontos_campeonato,
            "ATLETA_ID": aid,
            "APELIDO": a.get("apelido", ""),
            "NOME": a.get("nome", ""),
            "POSICAO_ID": a.get("posicao_id"),
            "CLUBE_ID": a.get("clube_id"),
            "PRECO": a.get("preco_num"),
            "PONTOS_ATLETA": a.get("pontos_num"),
            "SCOUTS": json.dumps(a.get("scout") or {}, ensure_ascii=False, separators=(",", ":")),
            "CAPITAO": "SIM" if aid == capitao_id else "NAO",
            "RESERVA": "SIM",
            "TECNICO": "SIM" if a.get("posicao_id") == 6 else "NAO",
            "ESQUEMA_ID": esquema_id,
            "PATRIMONIO": patrimonio,
            "VALOR_TIME": valor_time,
            "FONTE": fonte,
            "CAPTURADO_EM": gerado_em,
            "RAW_JSON_ATLETA": json.dumps(a, ensure_ascii=False, separators=(",", ":")),
        })
    return rows


def main():
    gerado_em = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    out = {"ano": 2026, "gerado_em_utc": gerado_em, "rodadas": {}}
    todas = []
    falhas = 0

    for rodada, time_id in MITOS.items():
        print(f"Buscando rodada {rodada}, time_id={time_id}", flush=True)
        res = buscar(rodada, time_id)
        out["rodadas"][str(rodada)] = {"time_id": time_id, **res}
        if not res.get("ok"):
            falhas += 1
        else:
            todas.extend(normalizar(rodada, time_id, res, gerado_em))
        time.sleep(0.4)

    data_dir = Path("data")
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "mito_escalacoes_2026.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    norm_dir = data_dir / "mitos_2026_normalizado"
    norm_dir.mkdir(parents=True, exist_ok=True)
    fields = [
        "ANO","RODADA","MITO_TIME_ID","MITO_NOME_TIME","MITO_PONTOS","MITO_PONTOS_CAMPEONATO",
        "ATLETA_ID","APELIDO","NOME","POSICAO_ID","CLUBE_ID","PRECO","PONTOS_ATLETA","SCOUTS",
        "CAPITAO","RESERVA","TECNICO","ESQUEMA_ID","PATRIMONIO","VALOR_TIME","FONTE","CAPTURADO_EM","RAW_JSON_ATLETA"
    ]
    for inicio in (1, 7, 13, 19):
        fim = inicio + 5
        arquivo = norm_dir / f"rodadas_{inicio:02d}_{fim:02d}.csv"
        subset = [r for r in todas if inicio <= r["RODADA"] <= fim]
        with arquivo.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(subset)
        print(f"Normalizado: {arquivo} | linhas={len(subset)}")

    print(f"Coleta concluída | linhas normalizadas={len(todas)} | falhas={falhas}")
    if falhas:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
