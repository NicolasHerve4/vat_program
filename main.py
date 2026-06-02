#!/usr/bin/env python3
# =============================================================================
# main.py  -  Point d'entree du controle TVA Business Central
#
# Usage :
#   python main.py                         # periode definie dans config.py
#   python main.py --from 2026-01-01 --to 2026-03-31
#   python main.py --probe                 # affiche les champs reels des services
#                                          # (pour ajuster config.py) puis quitte
#   python main.py --limit 100             # limite le nb de lignes (test rapide)
# =============================================================================
import argparse
import os
import sys

import pandas as pd

import config
from bc_client import BusinessCentralClient, build_period_filter
import reconciliation as rec


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Controle / reconciliation TVA Business Central (CA3-like)")
    p.add_argument("--from", dest="date_from", default=config.DATE_FROM, help="Date debut AAAA-MM-JJ")
    p.add_argument("--to", dest="date_to", default=config.DATE_TO, help="Date fin AAAA-MM-JJ")
    p.add_argument("--probe", action="store_true", help="Lister les champs reels des services OData et quitter")
    p.add_argument("--limit", type=int, default=None, help="Limiter le nombre de lignes (test)")
    p.add_argument("--out", dest="out_dir", default=config.OUTPUT_DIR, help="Dossier de sortie")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    client = BusinessCentralClient()

    gl_service = config.ODATA_SERVICES["gl_entries"]
    vat_service = config.ODATA_SERVICES["vat_entries"]

    # --- Mode diagnostic : afficher les champs reels et quitter ---
    if args.probe:
        print(f"\n== Champs du service GL '{gl_service}' ==")
        for f in client.probe(gl_service):
            print("  ", f)
        print(f"\n== Champs du service TVA '{vat_service}' ==")
        for f in client.probe(vat_service):
            print("  ", f)
        print("\nAjuste GL_FIELDS / VAT_FIELDS dans config.py avec ces noms exacts.")
        return 0

    # --- Filtre periode ---
    date_field_gl = config.GL_FIELDS["vat_date" if config.PERIOD_FIELD == "vat" else "posting_date"]
    date_field_vat = config.VAT_FIELDS["vat_date" if config.PERIOD_FIELD == "vat" else "posting_date"]
    filter_gl = build_period_filter(date_field_gl, args.date_from, args.date_to)
    filter_vat = build_period_filter(date_field_vat, args.date_from, args.date_to)

    print(f"Periode : {args.date_from} -> {args.date_to}  (champ: {config.PERIOD_FIELD})")

    # --- Extraction ---
    print(f"Extraction GL ('{gl_service}')...")
    gl_raw = client.fetch_service(
        gl_service, select=list(config.GL_FIELDS.values()),
        odata_filter=filter_gl, top=args.limit,
    )
    print(f"  {len(gl_raw)} ecritures comptables.")

    print(f"Extraction TVA ('{vat_service}')...")
    vat_raw = client.fetch_service(
        vat_service, select=list(config.VAT_FIELDS.values()),
        odata_filter=filter_vat, top=args.limit,
    )
    print(f"  {len(vat_raw)} ecritures TVA.")

    # --- Normalisation ---
    gl = rec.normalize_gl(gl_raw)
    vat = rec.normalize_vat(vat_raw)

    # --- Traitements ---
    recon_df = rec.reconcile_gl_vs_vat(gl, vat)
    ca3_df = rec.build_ca3(vat)
    ca3_det = rec.ca3_detail(vat)

    # --- Restitution console ---
    print("\n===== RECONCILIATION GRAND LIVRE <-> ECRITURES TVA =====")
    print(recon_df.to_string(index=False))
    print("\n===== ETAT CA3 (synthese) =====")
    print(ca3_df.to_string(index=False) if not ca3_df.empty else "(aucune ecriture TVA)")
    nb_non_mappe = int((ca3_det["ca3_line"] == config.CA3_FALLBACK_LINE["ca3_line"]).sum()) if not ca3_det.empty else 0
    if nb_non_mappe:
        print(f"\n[!] {nb_non_mappe} ecriture(s) TVA NON MAPPEE(S) (ligne "
              f"{config.CA3_FALLBACK_LINE['ca3_line']}) -> completer CA3_RULES dans config.py")

    # --- Exports ---
    export(args.out_dir, args.date_from, args.date_to, gl, vat, recon_df, ca3_df, ca3_det)
    return 0


def export(out_dir, date_from, date_to, gl, vat, recon_df, ca3_df, ca3_det) -> None:
    os.makedirs(out_dir, exist_ok=True)
    suffix = f"{date_from}_{date_to}"

    if config.OUTPUT_CSV:
        gl.to_csv(os.path.join(out_dir, f"gl_entries_{suffix}.csv"), index=False, encoding="utf-8-sig")
        vat.to_csv(os.path.join(out_dir, f"vat_entries_{suffix}.csv"), index=False, encoding="utf-8-sig")
        ca3_df.to_csv(os.path.join(out_dir, f"ca3_synthese_{suffix}.csv"), index=False, encoding="utf-8-sig")
        recon_df.to_csv(os.path.join(out_dir, f"reconciliation_{suffix}.csv"), index=False, encoding="utf-8-sig")
        print(f"\nCSV ecrits dans : {out_dir}/")

    if config.OUTPUT_EXCEL:
        xlsx_path = os.path.join(out_dir, f"controle_ca3_{suffix}.xlsx")
        with pd.ExcelWriter(xlsx_path, engine="openpyxl") as xl:
            recon_df.to_excel(xl, sheet_name="Reconciliation", index=False)
            ca3_df.to_excel(xl, sheet_name="CA3_synthese", index=False)
            ca3_det.to_excel(xl, sheet_name="CA3_detail", index=False)
            gl.to_excel(xl, sheet_name="GL_entries", index=False)
            vat.to_excel(xl, sheet_name="VAT_entries", index=False)
        print(f"Excel de controle : {xlsx_path}")


if __name__ == "__main__":
    try:
        sys.exit(main())
    except RuntimeError as e:
        print(f"\nERREUR : {e}", file=sys.stderr)
        sys.exit(1)
