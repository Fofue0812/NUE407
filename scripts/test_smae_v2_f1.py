#!/usr/bin/env python3
"""Pruebas F1 para App SMAE · INCAP v2.0 (D700 (2), especificación F1 §6).

Verifica con los datos reales de smae/datos/ y las claves de Evaluación:
  - Cobertura y exactitud de los 18 códigos INCAP del B3 (datos_ev1.py y datos_practica_v2.py)
  - B6 caso: sodio 397,1 mg (20 filas), potasio 1 740,2 mg, fósforo 754,2 mg (B6_calculo_v2.json)
  - B6 práctica: sodio 317,5 mg (15 filas)
  - Presencia de los 4 códigos ausentes (1015, 13175, 20006, 2002) y tortilla 14052 (Na 3 mg/100 g)
  - B5, B7 y B8: el cuadro por equivalentes de smae.json reproduce app_SMAE_recalculo_EV
  - 4 controles que deben fallar a propósito (--control):
      incap_alterado, fila_de_menos, sha_alterado, null_a_cero
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from decimal import Decimal, ROUND_HALF_UP
from fractions import Fraction as F
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DATOS = REPO / "smae" / "datos"

B3_EV1 = Path(r"E:\Google Drive\Claude outputs\Jornadas\20261125_U02_J2\evaluacion\scripts")
B6_JSON = Path(r"E:\Google Drive\Claude outputs\Jornadas\20261127_U02_J3\evaluacion\B6_calculo_v2.json")


def q(x, n: str = "0.1") -> Decimal:
    fr = F(x)
    return (Decimal(fr.numerator) / Decimal(fr.denominator)).quantize(
        Decimal(n), rounding=ROUND_HALF_UP
    )


def falla(msg: str) -> None:
    raise SystemExit("FALLA: " + msg)


def cargar_datos(ctl: str | None = None) -> tuple[dict, dict, dict, dict]:
    meta_bytes = (DATOS / "meta.json").read_bytes()
    smae_bytes = (DATOS / "smae.json").read_bytes()
    incap_bytes = (DATOS / "incap.json").read_bytes()

    if ctl == "sha_alterado":
        incap_bytes = incap_bytes.replace(b'"20006"', b'"20006"', 1) + b" "

    meta = json.loads(meta_bytes.decode("utf-8"))
    smae = json.loads(smae_bytes.decode("utf-8"))
    incap = json.loads(incap_bytes.decode("utf-8"))

    sha_smae = hashlib.sha256(smae_bytes).hexdigest()
    sha_incap = hashlib.sha256(incap_bytes).hexdigest()
    if sha_smae != meta["archivos"]["smae.json"]["sha256"]:
        falla("huella sha256 de smae.json no coincide con meta.json")
    if sha_incap != meta["archivos"]["incap.json"]["sha256"]:
        falla("huella sha256 de incap.json no coincide con meta.json")

    by_code = {str(r["codigo"]): r for r in incap["alimentos"]}
    if ctl == "incap_alterado":
        by_code["20006"] = dict(by_code["20006"], sodio=153)
    if ctl == "null_a_cero":
        # Buscar una fila con sodio=None y forzarlo a 0 sin que sea 0 en raw
        for r in incap["alimentos"]:
            if r["sodio"] is None and "sodio" not in (r.get("raw") or {}):
                by_code[str(r["codigo"])] = dict(r, sodio=0)
                break

    return meta, smae, incap, by_code


def verificar_sin_dato_fuente(by_code: dict) -> None:
    for cod, r in by_code.items():
        raw = r.get("raw") or {}
        for campo in ("agua", "energia", "proteina", "grasa_total", "carboh", "fibra", "calcio", "fosforo", "potasio", "sodio"):
            if campo not in raw and r[campo] is not None:
                falla(f"código {cod} campo {campo}: impreso vacío debe ser null (sin_dato_fuente), nunca {r[campo]}")
            if campo in raw and raw[campo] in ("0", "0.0", "0.00") and r[campo] != 0:
                falla(f"código {cod} campo {campo}: 0 impreso debe quedar como 0")


def verificar_b3(by_code: dict, ctl: str | None = None) -> None:
    sys.path.insert(0, str(B3_EV1))
    import datos_ev1 as A
    import datos_practica_v2 as B

    incap_ref = dict(A.INCAP)
    incap_ref.update(B.INCAP)
    filas = list(A.R) + list(B.R)
    if ctl == "fila_de_menos":
        filas = filas[:-1]
    if len(filas) != len(A.R) + len(B.R):
        falla(f"cobertura B3 incompleta: {len(filas)} filas != {len(A.R) + len(B.R)}")

    cods = sorted({r["codigo"] for r in filas})
    assert len(cods) == 18, f"Se esperaban 18 códigos B3, hay {len(cods)}"
    for c in cods:
        if c not in by_code:
            falla(f"código B3 {c} ausente en incap.json")
        _, pg, kcal_exp, prot_exp = incap_ref[c]
        row = by_code[c]
        if row["pagina"] != pg:
            falla(f"código {c}: página {row['pagina']} != {pg}")
        if q(str(row["energia"]), "0.1") != q(str(kcal_exp), "0.1"):
            falla(f"código {c}: energía {row['energia']} != {kcal_exp}")
        if q(str(row["proteina"]), "0.01") != q(str(prot_exp), "0.01"):
            falla(f"código {c}: proteína {row['proteina']} != {prot_exp}")

    # Valores explícitos de especificación §6
    assert by_code["3057"]["energia"] == 120 and q(str(by_code["3057"]["proteina"]), "0.01") == Decimal("22.50")
    assert by_code["14052"]["energia"] == 211 and q(str(by_code["14052"]["proteina"]), "0.01") == Decimal("4.91")


def verificar_b6(by_code: dict, smae: dict) -> None:
    d = json.loads(B6_JSON.read_text(encoding="utf-8"))
    for nom, filas, esp_na in (
        ("caso", d["filas_hilo"], Decimal("397.1")),
        ("práctica", d["filas_practica"], Decimal("317.5")),
    ):
        tot_na = F(0)
        tot_k = F(0)
        tot_p = F(0)
        for r in filas:
            cod = str(r["codigo"])
            if cod not in by_code:
                falla(f"código B6 {cod} ausente en incap.json")
            row = by_code[cod]
            g = F(str(r["g"]))
            tot_na += F(str(row["sodio"])) * g / 100
            tot_k += F(str(row["potasio"])) * g / 100
            tot_p += F(str(row["fosforo"])) * g / 100
        if q(tot_na) != esp_na:
            falla(f"el sodio de los alimentos del {nom} da {str(q(tot_na)).replace('.', ',')} y la pieza dice {str(esp_na).replace('.', ',')}")
        if nom == "caso":
            if q(tot_k) != Decimal("1740.2"):
                falla(f"potasio B6 caso da {q(tot_k)} != 1740.2")
            if q(tot_p) != Decimal("754.2"):
                falla(f"fósforo B6 caso da {q(tot_p)} != 754.2")

    # 4 códigos ausentes + 14052 presentes en incap.json y vinculados en smae.json / vinculos.csv
    assert by_code["14052"]["sodio"] == 3
    linked_codes = set()
    for f in smae["foods"]:
        if f.get("c"):
            linked_codes.add(str(f["c"]))
        for rc in f.get("incap_refs") or []:
            linked_codes.add(str(rc))
    for c in ("1015", "12165", "13175", "20006", "2002", "14052"):
        if c not in by_code:
            falla(f"código {c} ausente en incap.json")
        if c not in linked_codes:
            falla(f"código {c} sin vínculo en smae.json")

    with (DATOS / "vinculos.csv").open(encoding="utf-8") as fh:
        v_rows = list(csv.DictReader(fh))
    v_codes = {r["codigo_incap"] for r in v_rows}
    for c in ("1015", "12165", "13175", "20006", "2002"):
        if c not in v_codes:
            falla(f"vínculo U02 {c} ausente en vinculos.csv")


def verificar_b5_b7_b8(smae: dict) -> None:
    G = {g["k"]: {n: F(str(g[n])) for n in ("kcal", "p", "l", "hc")} for g in smae["groups"]}
    tot = lambda cu: {n: sum(F(x) * G[k][n] for k, x in cu.items()) for n in ("kcal", "p", "l", "hc")}
    b5 = dict(csg=11, leg=1, ver=2, aom=F(1, 2), len=1, asp=15, fru=3)
    assert q(tot(b5)["kcal"]) == Decimal("1982.5")
    assert q(tot(b5)["hc"] / 15) == Decimal("16.7")
    b5p = dict(csg=13, len=F(1, 2), leg=2, ver=2, aom=F(1, 2), fru=3, asp=15)
    assert q(tot(b5p)["kcal"]) == Decimal("2167.5")
    b7 = dict(aom=1, leg=1, ver=2, csg=8, fru=4, asg=6, asp=13)
    assert q(tot(b7)["kcal"]) == Decimal("1870.0")
    b7p = dict(csg=10, leg=1, ver=2, aom=1, fru=3, asg=6, asp=14)
    assert q(tot(b7p)["kcal"]) == Decimal("1995.0")
    b8_hd_10 = dict(leg=1, ver=2, aom=4, asp=10, fru=4, asg=2, csg=9)
    assert q(tot(b8_hd_10)["kcal"]) == Decimal("1870.0")
    b8_hd_12 = dict(leg=1, ver=2, aom=6, asp=8, fru=3, asg=4, csg=8)
    assert q(tot(b8_hd_12)["kcal"]) == Decimal("1880.0")
    b8_hd_alt = dict(csg=8, leg=1, ver=2, aom=3, len=1, asp=10, fru=3, asg=4)
    assert q(tot(b8_hd_alt)["kcal"]) == Decimal("1895.0")

    # Verificar estructura F1
    assert smae["capas"] == {"renal": {}}
    assert len(smae["foods"]) == 2876
    assert len({f["id"] for f in smae["foods"]}) == 2876
    for f in smae["foods"]:
        for k_proh in ("k", "p_min", "ca"):
            assert k_proh not in f, f"SMAE no debe contener {k_proh} (§3.3)"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--control",
        choices=("incap_alterado", "fila_de_menos", "sha_alterado", "null_a_cero"),
        default=None,
    )
    args = ap.parse_args()
    meta, smae, incap, by_code = cargar_datos(args.control)
    verificar_sin_dato_fuente(by_code)
    verificar_b3(by_code, args.control)
    verificar_b6(by_code, smae)
    verificar_b5_b7_b8(smae)
    print(
        f"SMAE_V2_F1_TESTS_OK (smae={meta['conteos']['smae_total']}, otros={meta['conteos']['otros_total']}, "
        f"incap={meta['conteos']['incap_total']}, vinculos={meta['conteos']['vinculos_total']})"
    )


if __name__ == "__main__":
    main()
