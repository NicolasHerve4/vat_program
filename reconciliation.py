# =============================================================================
# reconciliation.py  -  Logique de controle TVA
#   1) Normalise les donnees brutes OData en DataFrames propres
#   2) Reconcilie le grand livre (comptes de TVA) avec les ecritures TVA
#   3) Construit l'etat CA3 a partir des regles de config.py
# =============================================================================
from typing import List, Optional

import pandas as pd

import config


# --------------------------------------------------------------------------- #
# 1) NORMALISATION
# --------------------------------------------------------------------------- #
def _rename(records: List[dict], field_map: dict) -> pd.DataFrame:
    """Transforme une liste de dicts OData en DataFrame avec des noms logiques.

    field_map : {nom_logique: nom_odata}. Les champs OData absents sont crees
    a NaN pour que le reste du code ne plante pas si un champ n'est pas publie.
    """
    df = pd.DataFrame(records)
    rename = {}
    for logical, odata_name in field_map.items():
        if odata_name in df.columns:
            rename[odata_name] = logical
        else:
            df[logical] = pd.NA  # champ absent -> colonne vide
    df = df.rename(columns=rename)
    # On ne garde que les colonnes logiques connues
    keep = [c for c in field_map.keys() if c in df.columns]
    return df[keep].copy()


def normalize_gl(records: List[dict]) -> pd.DataFrame:
    df = _rename(records, config.GL_FIELDS)
    for col in ("amount", "vat_amount"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    for col in ("posting_date", "vat_date"):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    df["gl_account_no"] = df["gl_account_no"].astype(str)
    return df


def normalize_vat(records: List[dict]) -> pd.DataFrame:
    df = _rename(records, config.VAT_FIELDS)
    num_cols = [
        "base", "amount", "unrealized_base", "unrealized_amount",
        "remaining_unrealized_base", "remaining_unrealized_amount", "vat_pct",
    ]
    for col in num_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    for col in ("posting_date", "vat_date"):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    return df


# --------------------------------------------------------------------------- #
# 2) RECONCILIATION GRAND LIVRE <-> ECRITURES TVA
# --------------------------------------------------------------------------- #
def reconcile_gl_vs_vat(gl: pd.DataFrame, vat: pd.DataFrame) -> pd.DataFrame:
    """Compare, par categorie de TVA, le montant cote grand livre et cote
    ecritures TVA. Un ecart > tolerance signale une anomalie (ex : ecriture
    passee directement sur un compte de TVA sans mecanisme TVA).
    """
    rows = []

    # --- Cote grand livre : somme des montants sur les comptes de TVA ---
    gl_by_cat = {}
    for category, accounts in config.VAT_GL_ACCOUNTS.items():
        accts = [str(a) for a in accounts]
        mask = gl["gl_account_no"].isin(accts)
        gl_by_cat[category] = round(float(gl.loc[mask, "amount"].sum()), 2)

    # --- Cote ecritures TVA : TVA realisee (encaissement) collectee/deductible ---
    vat_collected = round(float(vat.loc[vat["type"] == "Sale", "amount"].sum()), 2)
    vat_deductible = round(float(vat.loc[vat["type"] == "Purchase", "amount"].sum()), 2)
    # TVA non encore realisee (sur encaissement) = reste a realiser
    vat_pending = 0.0
    if "remaining_unrealized_amount" in vat.columns:
        vat_pending = round(float(vat["remaining_unrealized_amount"].sum()), 2)

    # Note de signe : en compta BC, la TVA collectee est au credit (montant negatif
    # cote GL) et la TVA deductible au debit (positif). On compare donc en valeur
    # absolue pour rester lisible dans le controle.
    rows.append(_recon_row("TVA collectee (ventes)",
                           abs(gl_by_cat.get("collected", 0.0)), abs(vat_collected)))
    rows.append(_recon_row("TVA deductible (achats)",
                           abs(gl_by_cat.get("deductible", 0.0)), abs(vat_deductible)))
    rows.append(_recon_row("TVA en attente / sur encaissement",
                           abs(gl_by_cat.get("pending", 0.0)), abs(vat_pending)))

    return pd.DataFrame(rows)


def _recon_row(label: str, gl_amount: float, vat_amount: float) -> dict:
    ecart = round(gl_amount - vat_amount, 2)
    return {
        "Categorie": label,
        "Montant grand livre": gl_amount,
        "Montant ecritures TVA": vat_amount,
        "Ecart": ecart,
        "Statut": "OK" if abs(ecart) <= config.RECON_TOLERANCE else "ECART A INVESTIGUER",
    }


# --------------------------------------------------------------------------- #
# 3) CONSTRUCTION DE L'ETAT CA3
# --------------------------------------------------------------------------- #
def _matches(row: pd.Series, rule: dict) -> bool:
    """True si la ligne TVA satisfait tous les criteres renseignes de la regle."""
    for key in ("type", "vat_bus_group", "vat_prod_group", "vat_calc_type"):
        crit = rule.get(key)
        if crit is None:
            continue
        value = row.get(key)
        allowed = crit if isinstance(crit, (list, tuple, set)) else [crit]
        if value not in allowed:
            return False
    return True


def _amounts_for(row: pd.Series, amount_src: str):
    """Renvoie (base, tva) selon la source choisie (realise vs non realise)."""
    if amount_src == "unrealized":
        return (float(row.get("remaining_unrealized_base", 0.0) or 0.0),
                float(row.get("remaining_unrealized_amount", 0.0) or 0.0))
    return (float(row.get("base", 0.0) or 0.0),
            float(row.get("amount", 0.0) or 0.0))


def build_ca3(vat: pd.DataFrame) -> pd.DataFrame:
    """Ventile chaque ecriture TVA sur une ligne CA3 selon CA3_RULES.
    Toute ecriture non mappee tombe dans la ligne 'filet de securite'.
    """
    detail = []
    for _, row in vat.iterrows():
        matched = None
        for rule in config.CA3_RULES:
            if _matches(row, rule):
                matched = rule
                break
        if matched is None:
            matched = config.CA3_FALLBACK_LINE
        base, tva = _amounts_for(row, matched.get("amount_src", "realized"))
        detail.append({
            "ca3_line": matched["ca3_line"],
            "ca3_label": matched["ca3_label"],
            "type": row.get("type"),
            "vat_bus_group": row.get("vat_bus_group"),
            "vat_prod_group": row.get("vat_prod_group"),
            "base": round(base, 2),
            "tva": round(tva, 2),
        })

    detail_df = pd.DataFrame(detail)
    if detail_df.empty:
        return detail_df

    ca3 = (
        detail_df.groupby(["ca3_line", "ca3_label"], as_index=False)[["base", "tva"]]
        .sum()
        .sort_values("ca3_line")
        .reset_index(drop=True)
    )
    ca3["base"] = ca3["base"].round(2)
    ca3["tva"] = ca3["tva"].round(2)
    return ca3


def ca3_detail(vat: pd.DataFrame) -> pd.DataFrame:
    """Version detaillee (une ligne par ecriture TVA + sa ligne CA3 affectee),
    utile pour auditer le mapping et reperer les 'NON MAPPE'.
    """
    out = []
    for _, row in vat.iterrows():
        matched = next((r for r in config.CA3_RULES if _matches(row, r)),
                       config.CA3_FALLBACK_LINE)
        base, tva = _amounts_for(row, matched.get("amount_src", "realized"))
        rec = row.to_dict()
        rec["ca3_line"] = matched["ca3_line"]
        rec["ca3_label"] = matched["ca3_label"]
        rec["ca3_base"] = round(base, 2)
        rec["ca3_tva"] = round(tva, 2)
        out.append(rec)
    return pd.DataFrame(out)
