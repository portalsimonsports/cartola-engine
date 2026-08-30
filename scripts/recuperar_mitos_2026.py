import json
import os
import time
from pathlib import Path

import requests

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
                data = r.json()
                return {"ok": True, "url": url, "data": data}
            erros.append(f"{url} -> HTTP {r.status_code}: {r.text[:160]}")
        except Exception as e:
            erros.append(f"{url} -> {type(e).__name__}: {e}")
        time.sleep(0.5)
    return {"ok": False, "erros": erros}


def main():
    out = {
        "ano": 2026,
        "gerado_em_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "rodadas": {},
    }
    falhas = 0
    for rodada, time_id in MITOS.items():
        print(f"Buscando rodada {rodada}, time_id={time_id}", flush=True)
        res = buscar(rodada, time_id)
        out["rodadas"][str(rodada)] = {"time_id": time_id, **res}
        if not res.get("ok"):
            falhas += 1
        time.sleep(0.4)

    path = Path("data/mito_escalacoes_2026.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Arquivo gravado: {path} | falhas={falhas}")
    if falhas:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
