# =============================================================================
# test_mock.py  -  Valide la logique de reconciliation/CA3 SANS connexion BC.
# Utilise des donnees fictives au format OData pour verifier que le pipeline
# tourne et produit les bons fichiers de sortie.
#   python test_mock.py
# =============================================================================
import reconciliation as rec
import config

# --- Fausses ecritures comptables (format OData "brut") ---
GL_RAW = [
    {"Entry_No": 1, "G_L_Account_No": "44571", "Posting_Date": "2026-01-15",
     "VAT_Date": "2026-01-15", "Document_No": "VTE001", "Document_Type": "Invoice",
     "Description": "Vente", "Amount": -200.0, "VAT_Amount": -200.0,
     "Gen_Posting_Type": "Sale", "VAT_Bus_Posting_Group": "FR", "VAT_Prod_Posting_Group": "TVA20"},
    {"Entry_No": 2, "G_L_Account_No": "44566", "Posting_Date": "2026-01-20",
     "VAT_Date": "2026-01-20", "Document_No": "ACH001", "Document_Type": "Invoice",
     "Description": "Achat", "Amount": 80.0, "VAT_Amount": 80.0,
     "Gen_Posting_Type": "Purchase", "VAT_Bus_Posting_Group": "FR", "VAT_Prod_Posting_Group": "TVA20"},
    # TVA sur encaissement non encore realisee -> compte d'attente (DOM 8,5%)
    {"Entry_No": 3, "G_L_Account_No": "44574", "Posting_Date": "2026-01-22",
     "VAT_Date": "2026-01-22", "Document_No": "VTE002", "Document_Type": "Invoice",
     "Description": "TVA en attente", "Amount": -85.0, "VAT_Amount": -85.0,
     "Gen_Posting_Type": "Sale", "VAT_Bus_Posting_Group": "DOM", "VAT_Prod_Posting_Group": "TVA85"},
]

# --- Fausses ecritures TVA ---
VAT_RAW = [
    {"Entry_No": 1, "Posting_Date": "2026-01-15", "VAT_Date": "2026-01-15",
     "Document_No": "VTE001", "Document_Type": "Invoice", "Type": "Sale",
     "Base": 1000.0, "Amount": 200.0, "Unrealized_Base": 0.0, "Unrealized_Amount": 0.0,
     "Remaining_Unrealized_Base": 0.0, "Remaining_Unrealized_Amount": 0.0,
     "VAT_Calculation_Type": "Normal VAT", "VAT_Bus_Posting_Group": "FR",
     "VAT_Prod_Posting_Group": "TVA20", "Closed": True},
    {"Entry_No": 2, "Posting_Date": "2026-01-20", "VAT_Date": "2026-01-20",
     "Document_No": "ACH001", "Document_Type": "Invoice", "Type": "Purchase",
     "Base": 400.0, "Amount": 80.0, "Unrealized_Base": 0.0, "Unrealized_Amount": 0.0,
     "Remaining_Unrealized_Base": 0.0, "Remaining_Unrealized_Amount": 0.0,
     "VAT_Calculation_Type": "Normal VAT", "VAT_Bus_Posting_Group": "FR",
     "VAT_Prod_Posting_Group": "TVA20", "Closed": True},
    # Vente DOM-TOM 8,5% (TVA sur encaissement non encore realisee)
    {"Entry_No": 3, "Posting_Date": "2026-01-22", "VAT_Date": "2026-01-22",
     "Document_No": "VTE002", "Document_Type": "Invoice", "Type": "Sale",
     "Base": 0.0, "Amount": 0.0, "Unrealized_Base": 1000.0, "Unrealized_Amount": 85.0,
     "Remaining_Unrealized_Base": 1000.0, "Remaining_Unrealized_Amount": 85.0,
     "VAT_Calculation_Type": "Normal VAT", "VAT_Bus_Posting_Group": "DOM",
     "VAT_Prod_Posting_Group": "TVA85", "Closed": False},
    # Export hors UE (exonere)
    {"Entry_No": 4, "Posting_Date": "2026-01-25", "VAT_Date": "2026-01-25",
     "Document_No": "VTE003", "Document_Type": "Invoice", "Type": "Sale",
     "Base": 5000.0, "Amount": 0.0, "Unrealized_Base": 0.0, "Unrealized_Amount": 0.0,
     "Remaining_Unrealized_Base": 0.0, "Remaining_Unrealized_Amount": 0.0,
     "VAT_Calculation_Type": "Normal VAT", "VAT_Bus_Posting_Group": "EXPORT",
     "VAT_Prod_Posting_Group": "EXO", "Closed": True},
]


def main():
    gl = rec.normalize_gl(GL_RAW)
    vat = rec.normalize_vat(VAT_RAW)

    recon_df = rec.reconcile_gl_vs_vat(gl, vat)
    ca3_df = rec.build_ca3(vat)
    ca3_det = rec.ca3_detail(vat)

    print("===== RECONCILIATION =====")
    print(recon_df.to_string(index=False))
    print("\n===== CA3 SYNTHESE =====")
    print(ca3_df.to_string(index=False))
    print("\n===== CA3 DETAIL (lignes affectees) =====")
    print(ca3_det[["entry_no", "type", "vat_bus_group", "vat_prod_group",
                   "ca3_line", "ca3_label", "ca3_base", "ca3_tva"]].to_string(index=False))

    # Verifs basiques
    assert (recon_df["Statut"] == "OK").all(), "La reconciliation devrait etre OK sur ce jeu fictif"
    assert not ca3_df.empty, "La CA3 ne devrait pas etre vide"
    print("\nOK - logique validee sur donnees fictives.")


if __name__ == "__main__":
    main()
