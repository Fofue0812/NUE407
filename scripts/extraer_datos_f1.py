#!/usr/bin/env python3
"""Extracción F1 para App SMAE · INCAP v2.0 (D982, especificación F1 Apps).

Genera en smae/datos/:
  - incap.json (Extracción A de INCAP 2018 3.ª ed., todas las filas y columnas)
  - smae.json (separación de DATA v0.6.11 con IDs estables, na_estado, incap_ref, capas.renal vacía)
  - meta.json (versión, fecha, sha256 de smae.json e incap.json, conteos y config.datos_base)
  - vinculos.csv (188 existentes + 5 vínculos U02: 1015, 12165, 13175, 20006, 2002)
  - sodio_215_estado.csv (215 alimentos sin sodio del SMAE en estado por_revisar)
  - discrepancias_extraccion.csv (plantilla vacía para cotejo con Extracción B de Science)
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
from pathlib import Path

import pymupdf

PDF_INCAP = Path(
    r"E:\Google Drive\01 🏛️ House of Wisdom\01_Artículos\Nutrición\14 Alimentos, composición y microbiota"
    r"\tabladecomposiciondealimentos-240629181100-a6fb3514.pdf"
)
REPO = Path(__file__).resolve().parent.parent
SMAE_DIR = REPO / "smae"
DATOS_DIR = SMAE_DIR / "datos"
INDEX_HTML = SMAE_DIR / "index.html"

# Coordenadas X centrales de cada columna en MACRONUTRIENTES Y MINERALES (verificadas en p.26, p.38, p.162)
COLS_MACRO = {
    "agua": 350.0,
    "energia": 376.0,
    "proteina": 404.0,
    "grasa_total": 438.0,
    "ag_sat": 469.0,
    "ag_mono": 497.0,
    "ag_poli": 526.0,
    "colesterol": 556.0,
    "carboh": 582.0,
    "azucares": 615.0,
    "ceniza": 642.0,
    "fibra": 670.0,
    "calcio": 700.0,
    "hierro": 729.0,
    "magnesio": 756.0,
    "fosforo": 779.0,
    "potasio": 809.0,
    "sodio": 840.0,
    "zinc": 866.0,
    "cobre": 895.0,
    "selenio": 931.0,
    "fraccion_comestible": 962.0,
}

# Columnas en VITAMINAS (páginas impares 27..297, verificadas en p.51)
COLS_VIT = {
    "energia_vit": 357.7,
    "vit_c": 394.7,
    "tiamina": 422.4,
    "riboflavina": 455.2,
    "niacina": 488.1,
    "ac_pantotenico": 523.2,
    "vit_b6": 553.9,
    "ac_folico": 582.9,
    "folato_alim": 615.0,
    "folato_fde": 648.7,
    "vit_b12": 685.4,
    "vit_a_ear": 720.4,
    "retinol": 756.4,
    "b_carotenos": 786.2,
    "vit_e": 813.1,
    "vit_d": 846.0,
    "vit_k": 882.9,
    "fraccion_comestible_vit": 923.6,
}

CAMPOS_PRINCIPALES = (
    "agua",
    "energia",
    "proteina",
    "grasa_total",
    "carboh",
    "fibra",
    "calcio",
    "fosforo",
    "potasio",
    "sodio",
)

RE_CODIGO = re.compile(r"^\d{3,6}$")
RE_NUMERO = re.compile(r"^\d+(?:\.\d+)?$")

# Vínculos nuevos de la U02 (§3.4 de 02_especificacion_F1.md)
VINCULOS_U02 = [
    ("384", "Leche entera", 135, "1015"),
    ("1057", "Plátano Macho", 36, "12165"),
    ("1807", "Arroz cocido", 42, "13175"),
    ("1536", "Caldo de pollo", 189, "20006"),
    ("139", "Huevo entero fresco", 117, "2002"),
]


def parse_num(tok: str | None) -> int | float | None:
    if tok is None:
        return None
    tok = tok.strip()
    if not tok or tok in ("-", "—", "---"):
        return None
    if not RE_NUMERO.match(tok):
        return None
    return float(tok) if "." in tok else int(tok)


def extraer_incap() -> dict:
    if not PDF_INCAP.is_file():
        raise FileNotFoundError(f"No existe el PDF INCAP en {PDF_INCAP}")
    pdf_sha = hashlib.sha256(PDF_INCAP.read_bytes()).hexdigest()
    doc = pymupdf.open(PDF_INCAP)

    rows_by_code: dict[str, dict] = {}
    orden: list[str] = []

    for pno in range(25, 297):
        page = doc[pno]
        text = page.get_text("text")
        is_macro = "MACRONUTRIENTES Y MINERALES" in text
        is_vit = ("VITAMINAS" in text) and ("NOMBRE DEL ALIMENTO" in text)
        if not is_macro and not is_vit:
            continue

        ws = page.get_text("words")
        codes = sorted(
            [w for w in ws if w[0] < 75 and w[1] > 140 and RE_CODIGO.match(w[4])],
            key=lambda w: w[1],
        )

        cols_map = COLS_MACRO if is_macro else COLS_VIT

        for idx, cw in enumerate(codes):
            y = cw[1]
            y_next = codes[idx + 1][1] if idx + 1 < len(codes) else y + 30
            same = [w for w in ws if abs(w[1] - y) <= 2.8]

            code = cw[4]
            if is_macro:
                name_ws = [
                    w
                    for w in ws
                    if 70 < w[0] < 330 and (y - 2.8) <= w[1] < min(y_next - 2.5, y + 18)
                ]
                name_ws.sort(key=lambda w: (round(w[1], 1), w[0]))
                nombre = " ".join(w[4] for w in name_ws).strip()

                raw_vals: dict[str, str] = {}
                for w in same:
                    if w[0] < 330:
                        continue
                    xc = (w[0] + w[2]) / 2
                    col = min(cols_map, key=lambda c: abs(cols_map[c] - xc))
                    raw_vals[col] = w[4]

                entry = {
                    "codigo": code,
                    "nombre": nombre,
                    "pagina": pno + 1,
                    "pagina_vit": None,
                }
                for col in CAMPOS_PRINCIPALES:
                    entry[col] = parse_num(raw_vals.get(col))
                extras = {}
                for col in COLS_MACRO:
                    if col not in CAMPOS_PRINCIPALES:
                        extras[col] = parse_num(raw_vals.get(col))
                entry["extras"] = extras
                entry["raw"] = raw_vals
                rows_by_code[code] = entry
                orden.append(code)
            else:
                if code not in rows_by_code:
                    continue
                raw_vit: dict[str, str] = {}
                for w in same:
                    if w[0] < 330:
                        continue
                    xc = (w[0] + w[2]) / 2
                    col = min(cols_map, key=lambda c: abs(cols_map[c] - xc))
                    raw_vit[col] = w[4]
                entry = rows_by_code[code]
                entry["pagina_vit"] = pno + 1
                for col in COLS_VIT:
                    entry["extras"][col] = parse_num(raw_vit.get(col))
                entry["raw"].update(raw_vit)

    alimentos = [rows_by_code[c] for c in orden]
    return {
        "fuente": "INCAP (2018), Tabla de composición de alimentos de Centroamérica, 3.ª ed.",
        "pdf_sha256": pdf_sha,
        "regla_nulos": "null equivale a sin_dato_fuente en la tabla impresa; 0 equivale a 0 impreso.",
        "alimentos": alimentos,
    }


def extraer_smae_base() -> tuple[dict, str]:
    raw_bytes = INDEX_HTML.read_bytes().replace(b"\r\n", b"\n")
    sha_lf = hashlib.sha256(raw_bytes).hexdigest()
    txt = raw_bytes.decode("utf-8")
    marker = "const DATA = "
    idx = txt.find(marker)
    if idx < 0:
        raise RuntimeError("No se encontró 'const DATA = ' en smae/index.html")
    data, _ = json.JSONDecoder().raw_decode(txt[idx + len(marker) :])
    return data, sha_lf


def asignar_ids_y_enlaces(data: dict, incap_codes: set[str]) -> tuple[dict, list[dict], list[dict]]:
    foods = data["foods"]
    seen_ids: set[str] = set()
    page_seq: dict[tuple[str, str], int] = {}

    vinculos_rows: list[dict] = []
    sin_na_rows: list[dict] = []

    # Mapa rápido de índices para verificar coincidencias U02
    u02_by_idx = {int(idx_s): (s_nom, pg, cod) for idx_s, s_nom, pg, cod in VINCULOS_U02}

    for i, f in enumerate(foods):
        g = f["g"]
        pg_key = str(f["pg"]) if f.get("pg") is not None else (f.get("src") or "otros")
        k = (g, pg_key)
        page_seq[k] = page_seq.get(k, 0) + 1
        fid = f"{g}-p{pg_key}-{page_seq[k]:02d}"
        assert fid not in seen_ids, f"ID duplicado: {fid}"
        seen_ids.add(fid)
        f["id"] = fid

        # Garantizar que k, p, ca NO existan en SMAE (§3.3)
        for forbidden in ("k", "p_min", "ca"):
            f.pop(forbidden, None)

        orig_c = (f.get("c") or "").strip()
        refs: list[str] = [orig_c] if orig_c else []

        if i in u02_by_idx:
            s_nom, pg_esp, cod_u02 = u02_by_idx[i]
            assert f["s"] == s_nom and f["pg"] == pg_esp, (
                f"Mismatch índice {i}: {f['s']} p.{f['pg']} != {s_nom} p.{pg_esp}"
            )
            assert cod_u02 in incap_codes, f"Código U02 {cod_u02} ausente en INCAP"
            if cod_u02 not in refs:
                refs.append(cod_u02)
            if not orig_c:
                f["c"] = cod_u02
            vinculos_rows.append(
                {
                    "alimento_smae": f["s"],
                    "pagina_smae": f["pg"],
                    "id_smae": fid,
                    "codigo_incap": cod_u02,
                    "propuesto_por": "Apps / Antigravity (F1 §3.4)",
                    "verificado_por": "PENDIENTE Science",
                    "fecha": "2026-11-26",
                    "estado": "propuesto_f1_pendiente_science",
                }
            )

        if orig_c:
            vinculos_rows.append(
                {
                    "alimento_smae": f["s"],
                    "pagina_smae": f["pg"] if f.get("pg") is not None else "INCAP/GASS",
                    "id_smae": fid,
                    "codigo_incap": orig_c,
                    "propuesto_por": "v0.6.11 (D228)",
                    "verificado_por": "Auditoría v0.6.9/v0.6.11",
                    "fecha": "2026-11-11",
                    "estado": "existente_v0.6.11",
                }
            )

        if refs:
            f["incap_refs"] = refs

        if f.get("na") is None:
            f["na_estado"] = "por_revisar"
            incap_ref = refs[-1] if refs else ""
            if incap_ref:
                f["incap_ref"] = incap_ref
            sin_na_rows.append(
                {
                    "id_smae": fid,
                    "alimento_smae": f["s"],
                    "grupo": g,
                    "pagina_smae": f.get("pg") if f.get("pg") is not None else "",
                    "estado": "por_revisar",
                    "incap_ref": incap_ref,
                }
            )
        else:
            f["na_estado"] = "verificado"

    smae_out = {
        "gnotes": data["gnotes"],
        "groups": data["groups"],
        "foods": foods,
        "ref": data["ref"],
        "pes": data["pes"],
        "glos": data["glos"],
        "capas": {"renal": {}},
    }
    return smae_out, vinculos_rows, sin_na_rows


def write_json(path: Path, obj: dict) -> str:
    txt = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    path.write_bytes(txt.encode("utf-8"))
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    DATOS_DIR.mkdir(parents=True, exist_ok=True)
    incap_data = extraer_incap()
    incap_codes = {r["codigo"] for r in incap_data["alimentos"]}
    smae_base, base_sha = extraer_smae_base()
    smae_out, vinculos_rows, sin_na_rows = asignar_ids_y_enlaces(smae_base, incap_codes)

    sha_smae = write_json(DATOS_DIR / "smae.json", smae_out)
    sha_incap = write_json(DATOS_DIR / "incap.json", incap_data)

    with (DATOS_DIR / "vinculos.csv").open("w", encoding="utf-8", newline="\n") as fh:
        w = csv.DictWriter(
            fh,
            fieldnames=[
                "alimento_smae",
                "pagina_smae",
                "id_smae",
                "codigo_incap",
                "propuesto_por",
                "verificado_por",
                "fecha",
                "estado",
            ],
        )
        w.writeheader()
        w.writerows(vinculos_rows)

    with (DATOS_DIR / "sodio_215_estado.csv").open("w", encoding="utf-8", newline="\n") as fh:
        w = csv.DictWriter(
            fh,
            fieldnames=["id_smae", "alimento_smae", "grupo", "pagina_smae", "estado", "incap_ref"],
        )
        w.writeheader()
        w.writerows(sin_na_rows)

    with (DATOS_DIR / "discrepancias_extraccion.csv").open("w", encoding="utf-8", newline="\n") as fh:
        w = csv.writer(fh)
        w.writerow(["codigo", "columna", "valor_A", "valor_B", "pagina", "estado", "resolucion_science"])

    smae_only = sum(1 for f in smae_out["foods"] if not f.get("src"))
    otros_total = len(smae_out["foods"]) - smae_only
    meta = {
        "version": "2.0.0-f1",
        "fecha": "2026-11-26",
        "base_v0611_sha256": base_sha,
        "modo_discordancia": "dos_cifras_color",
        "config": {"datos_base": "datos/"},
        "archivos": {
            "smae.json": {"sha256": sha_smae, "filas": len(smae_out["foods"])},
            "incap.json": {
                "sha256": sha_incap,
                "filas": len(incap_data["alimentos"]),
                "pdf_sha256": incap_data["pdf_sha256"],
            },
        },
        "conteos": {
            "smae_total": smae_only,
            "otros_total": otros_total,
            "foods_total": len(smae_out["foods"]),
            "incap_total": len(incap_data["alimentos"]),
            "sin_sodio_total": len(sin_na_rows),
            "vinculos_total": len(vinculos_rows),
        },
    }
    sha_meta = write_json(DATOS_DIR / "meta.json", meta)
    print(json.dumps({"meta_sha256": sha_meta, "conteos": meta["conteos"], "archivos": meta["archivos"]}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
