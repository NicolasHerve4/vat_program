# =============================================================================
# config.py  -  LE FICHIER VARIABLE
# -----------------------------------------------------------------------------
# Tout ce que tu dois ajuster pour ton environnement est ICI.
# Le reste du code (bc_client.py, reconciliation.py, main.py) n'a pas a etre
# modifie : il lit ces variables.
#
# Contexte pris en compte :
#   - TVA sur encaissement (TVA non realisee / "unrealized VAT")
#   - Ventes monde entier (export, intracommunautaire)
#   - DOM-TOM (taux specifiques Guadeloupe/Martinique/Reunion, Guyane/Mayotte HT)
#   - Sortie type controle CA3
# =============================================================================

# -----------------------------------------------------------------------------
# 1) SERVICES WEB ODATA PUBLIES DANS BUSINESS CENTRAL
# -----------------------------------------------------------------------------
# Renseigne ici le NOM EXACT de tes services web OData publies
# (BC : page "Services Web", colonne "Nom du service").
# Le code interroge :  .../ODataV4/Company('...')/<NomDuService>
ODATA_SERVICES = {
    "gl_entries":  "GeneralLedgerEntries",   # page "Ecritures comptables" (17)
    "vat_entries": "VATEntries",             # page "Ecritures TVA" (315/254)
}

# -----------------------------------------------------------------------------
# 2) PERIODE A EXTRAIRE (peut etre surchargee en ligne de commande)
# -----------------------------------------------------------------------------
# Format ISO AAAA-MM-JJ. La reconciliation TVA s'appuie sur la VAT Date.
DATE_FROM = "2026-01-01"
DATE_TO   = "2026-01-31"

# Sur quel champ filtrer la periode :
#   "vat"     -> filtre sur la Date de TVA (recommande pour la CA3)
#   "posting" -> filtre sur la Date de validation
PERIOD_FIELD = "vat"

# -----------------------------------------------------------------------------
# 3) MAPPING DES CHAMPS ODATA
# -----------------------------------------------------------------------------
# Les noms de champs OData de BC = la legende du champ, espaces et caracteres
# speciaux remplaces par "_". Verifie-les via :
#   <base_url>/<NomDuService>?$top=1   (regarde les cles JSON renvoyees)
# et ajuste si besoin.

# --- Ecritures comptables (GL Entries) ---
GL_FIELDS = {
    "entry_no":            "Entry_No",
    "gl_account_no":       "G_L_Account_No",
    "posting_date":        "Posting_Date",
    "vat_date":            "VAT_Date",
    "document_no":         "Document_No",
    "document_type":       "Document_Type",
    "description":         "Description",
    "amount":              "Amount",
    "vat_amount":          "VAT_Amount",
    "gen_posting_type":    "Gen_Posting_Type",      # Sale / Purchase
    "vat_bus_group":       "VAT_Bus_Posting_Group",
    "vat_prod_group":      "VAT_Prod_Posting_Group",
}

# --- Ecritures TVA (VAT Entries) ---
# On inclut les champs "non realise" indispensables a la TVA sur encaissement.
VAT_FIELDS = {
    "entry_no":                  "Entry_No",
    "posting_date":              "Posting_Date",
    "vat_date":                  "VAT_Date",
    "document_no":               "Document_No",
    "document_type":             "Document_Type",
    "type":                      "Type",                 # Sale / Purchase / Settlement
    "base":                      "Base",                 # base realisee
    "amount":                    "Amount",               # TVA realisee
    "unrealized_base":           "Unrealized_Base",
    "unrealized_amount":         "Unrealized_Amount",
    "remaining_unrealized_base": "Remaining_Unrealized_Base",
    "remaining_unrealized_amount":"Remaining_Unrealized_Amount",
    "vat_calc_type":             "VAT_Calculation_Type", # Normal / Reverse Charge / Full / Sales Tax
    "vat_bus_group":             "VAT_Bus_Posting_Group",
    "vat_prod_group":            "VAT_Prod_Posting_Group",
    "vat_pct":                   "VAT_",                 # souvent "VAT_%" -> "VAT_" ; a verifier
    "gl_account_no":             "G_L_Acc__No_",         # compte de regroupement TVA si dispo
    "closed":                    "Closed",
}

# -----------------------------------------------------------------------------
# 4) COMPTES DE TVA DU GRAND LIVRE (pour le rapprochement GL <-> ecritures TVA)
# -----------------------------------------------------------------------------
# Liste des numeros de comptes GL ou la TVA est comptabilisee.
# Adapte a TON plan comptable (exemples plan francais ci-dessous).
VAT_GL_ACCOUNTS = {
    # TVA collectee
    "collected": ["44571", "445710", "445711", "445712"],
    # TVA deductible
    "deductible": ["44566", "445660", "445620", "44562"],
    # TVA en attente / sur encaissement (non realisee) - TVA sur encaissement
    "pending": ["44574", "4458", "44587"],
    # TVA a decaisser / credit de TVA
    "settlement": ["44551", "44567"],
}

# Tolerance d'ecart (en valeur absolue) au-dela de laquelle on signale un ecart.
RECON_TOLERANCE = 0.01

# -----------------------------------------------------------------------------
# 5) MAPPING CA3  (le coeur du controle)
# -----------------------------------------------------------------------------
# Chaque regle associe une combinaison d'ecritures TVA a une LIGNE de la CA3.
# Une regle "matche" si TOUS les criteres renseignes correspondent
# (un critere a None = ignore). Les listes acceptent plusieurs valeurs.
#
# Champs disponibles pour les criteres :
#   type            : "Sale" / "Purchase"
#   vat_bus_group   : code Groupe compta. marche TVA (ex "FR","UE","EXPORT","DOM")
#   vat_prod_group  : code Groupe compta. produit TVA (ex "TVA20","TVA85","EXO")
#   vat_calc_type   : "Normal VAT" / "Reverse Charge VAT" / "Full VAT" ...
#
# "ca3_line"  : numero/case CA3 (texte libre, adapte a ton imprime CA3)
# "ca3_label" : libelle lisible
# "amount_src": quelle valeur sommer pour la TVA :
#       "realized"   -> champ Amount (TVA realisee, encaissement) [defaut CA3]
#       "unrealized" -> Remaining_Unrealized_Amount (TVA en attente)
# La base est prise dans le champ correspondant (Base / Remaining_Unrealized_Base).
#
# >>> AJUSTE CES REGLES POUR CALER SUR TON IMPRIME / FICHIER DE CONTROLE CA3 <<<
CA3_RULES = [
    # ---------------- TVA COLLECTEE (ventes) - operations imposables ----------
    {"type": "Sale",  "vat_bus_group": ["FR", "NATIONAL"], "vat_prod_group": ["TVA20"],
     "ca3_line": "08", "ca3_label": "Taux normal 20% (metropole)", "amount_src": "realized"},
    {"type": "Sale",  "vat_bus_group": ["FR", "NATIONAL"], "vat_prod_group": ["TVA10"],
     "ca3_line": "9B", "ca3_label": "Taux 10% (metropole)", "amount_src": "realized"},
    {"type": "Sale",  "vat_bus_group": ["FR", "NATIONAL"], "vat_prod_group": ["TVA55"],
     "ca3_line": "09", "ca3_label": "Taux 5,5% (metropole)", "amount_src": "realized"},
    {"type": "Sale",  "vat_bus_group": ["FR", "NATIONAL"], "vat_prod_group": ["TVA21"],
     "ca3_line": "9B", "ca3_label": "Taux 2,1% (metropole)", "amount_src": "realized"},

    # ---------------- DOM-TOM (taux specifiques) ------------------------------
    # Guadeloupe / Martinique / Reunion : 8,5% normal, 2,1% reduit
    {"type": "Sale",  "vat_bus_group": ["DOM", "DOM85"], "vat_prod_group": ["TVA85"],
     "ca3_line": "13", "ca3_label": "DOM - taux 8,5%", "amount_src": "realized"},
    {"type": "Sale",  "vat_bus_group": ["DOM", "DOM85"], "vat_prod_group": ["TVA21"],
     "ca3_line": "13", "ca3_label": "DOM - taux 2,1%", "amount_src": "realized"},
    # Guyane / Mayotte : TVA non applicable (operations non imposables -> ligne 05)
    {"type": "Sale",  "vat_bus_group": ["DOM_HT", "GUYANE", "MAYOTTE"], "vat_prod_group": None,
     "ca3_line": "05", "ca3_label": "DOM hors champ (Guyane/Mayotte)", "amount_src": "realized"},

    # ---------------- OPERATIONS NON TAXEES (monde) ---------------------------
    {"type": "Sale",  "vat_bus_group": ["EXPORT", "MONDE"], "vat_prod_group": None,
     "ca3_line": "04", "ca3_label": "Exportations hors UE", "amount_src": "realized"},
    {"type": "Sale",  "vat_bus_group": ["UE", "INTRA"], "vat_prod_group": None,
     "ca3_line": "06", "ca3_label": "Livraisons intracommunautaires", "amount_src": "realized"},

    # ---------------- TVA DEDUCTIBLE (achats) ---------------------------------
    {"type": "Purchase", "vat_bus_group": None, "vat_prod_group": ["IMMO", "TVA20IMMO"],
     "ca3_line": "19", "ca3_label": "TVA deductible sur immobilisations", "amount_src": "realized"},
    {"type": "Purchase", "vat_bus_group": None, "vat_prod_group": None,
     "ca3_line": "20", "ca3_label": "TVA deductible sur autres biens et services", "amount_src": "realized"},

    # ---------------- AUTOLIQUIDATION (reverse charge UE/import) ---------------
    {"type": "Purchase", "vat_bus_group": ["UE", "INTRA"], "vat_calc_type": ["Reverse Charge VAT"],
     "vat_prod_group": None,
     "ca3_line": "3B", "ca3_label": "Acquisitions intracommunautaires (autoliquidation)", "amount_src": "realized"},
]

# Regle "filet de securite" : toute ecriture TVA qui ne matche AUCUNE regle
# ci-dessus est versee dans cette ligne pour ne RIEN perdre dans le controle.
CA3_FALLBACK_LINE = {"ca3_line": "ZZ", "ca3_label": "NON MAPPE - a classer", "amount_src": "realized"}

# -----------------------------------------------------------------------------
# 6) SORTIE
# -----------------------------------------------------------------------------
OUTPUT_DIR = "output"
OUTPUT_EXCEL = True   # genere un .xlsx multi-onglets de controle
OUTPUT_CSV   = True   # genere des CSV bruts (pour Power BI)
