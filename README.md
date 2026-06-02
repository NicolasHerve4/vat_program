# Contrôle TVA Business Central — Réconciliation GL ↔ Écritures TVA (CA3-like)

Programme Python qui se connecte à l'API **Business Central (SaaS)** en **OData V4 / OAuth2**, extrait les **écritures comptables** et les **écritures TVA**, puis produit :

- une **réconciliation** grand livre (comptes de TVA) ↔ table des écritures TVA,
- un **état CA3** (synthèse + détail), paramétrable ligne par ligne,
- des sorties **Excel multi-onglets** (contrôle) et **CSV** (pour Power BI).

Conçu pour : **TVA sur encaissement** (TVA non réalisée), **ventes monde entier** (export, intracommunautaire) et **DOM-TOM**.

---

## 1. Installation

```bash
pip install -r requirements.txt
```

## 2. Configuration

### a) Secrets de connexion → `.env`
```bash
cp .env.example .env
```
Renseigne `BC_TENANT_ID`, `BC_CLIENT_ID`, `BC_CLIENT_SECRET`, `BC_ENVIRONMENT`, `BC_COMPANY_NAME`.

> L'app Entra ID doit avoir la permission API `Dynamics 365 Business Central` et être autorisée dans BC (page **Utilisateurs Microsoft Entra** / **API**).

### b) Tout le reste → `config.py` (le « fichier variable »)
C'est **le seul fichier à ajuster** au quotidien :
- `ODATA_SERVICES` : noms exacts de tes services web OData publiés.
- `DATE_FROM` / `DATE_TO` / `PERIOD_FIELD` : période et champ de filtrage.
- `GL_FIELDS` / `VAT_FIELDS` : correspondance noms logiques ↔ noms OData réels.
- `VAT_GL_ACCOUNTS` : tes comptes de TVA (collectée, déductible, en attente, règlement).
- `CA3_RULES` : **le mapping CA3** — combinaisons (type, groupe marché, groupe produit, calcul) → ligne CA3.

## 3. Pré-requis côté Business Central

L'API standard **n'expose pas** la table *VAT Entries*. Publie deux services web OData (page **Services Web**) :

| Service à publier | Page BC |
| --- | --- |
| `GeneralLedgerEntries` | Écritures comptables (17) |
| `VATEntries` | Écritures TVA (315 / liste 254) |

## 4. Utilisation

```bash
# 1) Vérifier les noms de champs réels des services (puis ajuster config.py)
python main.py --probe

# 2) Lancer le contrôle sur la période de config.py
python main.py

# 3) Sur une période précise
python main.py --from 2026-01-01 --to 2026-03-31

# 4) Test rapide (limite le nb de lignes)
python main.py --limit 100
```

Sorties dans `output/` : `controle_ca3_<periode>.xlsx` + CSV.

## 5. Tester sans connexion BC

```bash
python test_mock.py
```
Valide la logique de réconciliation et de CA3 sur des données fictives.

---

## 6. TVA sur encaissement — note importante

En TVA sur encaissement, la TVA devient exigible **au paiement**, pas à la facture. BC gère cela via la **TVA non réalisée** (*Unrealized VAT*). Le code distingue :

- `Amount` / `Base` = TVA **réalisée** (encaissée) → c'est la base de la **CA3** (`amount_src: "realized"`),
- `Remaining_Unrealized_Amount` / `_Base` = TVA **en attente** d'encaissement → suivie à part dans la réconciliation, et mobilisable dans une règle CA3 via `amount_src: "unrealized"`.

## 7. Adapter à ton fichier de contrôle CA3

Le mapping `CA3_RULES` est un **point de départ**. Pour reproduire exactement ton fichier de contrôle :
1. Récupère ton fichier de contrôle CA3 de référence.
2. Aligne les **numéros/cases de ligne** (`ca3_line`) et libellés sur cet imprimé.
3. Vérifie que chaque combinaison (groupe marché × produit) de ton paramétrage BC a bien une règle ; sinon elle tombe en ligne `ZZ — NON MAPPE` (signalée à l'exécution).

## 8. Structure du projet

```
bc_vat_reconciliation/
├── .env.example        # modèle de secrets (à copier en .env)
├── config.py           # ★ fichier variable : tout se règle ici
├── bc_client.py        # connexion OAuth2 + lecture OData (pagination, probe)
├── reconciliation.py   # normalisation + réconciliation + construction CA3
├── main.py             # orchestration CLI + exports Excel/CSV
├── test_mock.py        # test de la logique sans BC
├── requirements.txt
└── README.md
```

> ⚠️ Vérifie toujours le mapping CA3 et les écarts de réconciliation avant tout usage déclaratif. Cet outil est une aide au contrôle, pas un validateur fiscal officiel.
