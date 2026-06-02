# =============================================================================
# bc_client.py  -  Connexion a l'API Business Central (SaaS) en OData V4
# Authentification OAuth2 client_credentials (Entra ID).
# Pas besoin de modifier ce fichier : tout est pilote par config.py / .env
# =============================================================================
import os
import time
import urllib.parse
from typing import Dict, List, Optional

import requests
from dotenv import load_dotenv

load_dotenv()

TOKEN_URL_TMPL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
ODATA_BASE_TMPL = (
    "https://api.businesscentral.dynamics.com/v2.0/{tenant}/{env}"
    "/ODataV4/Company('{company}')"
)


class BusinessCentralClient:
    """Client minimal pour lire des services web OData de Business Central."""

    def __init__(self) -> None:
        self.tenant = _require_env("BC_TENANT_ID")
        self.client_id = _require_env("BC_CLIENT_ID")
        self.client_secret = _require_env("BC_CLIENT_SECRET")
        self.environment = _require_env("BC_ENVIRONMENT")
        self.company = _require_env("BC_COMPANY_NAME")
        self.scope = os.getenv("BC_SCOPE", "https://api.businesscentral.dynamics.com/.default")

        self._token: Optional[str] = None
        self._token_expiry: float = 0.0

        company_enc = urllib.parse.quote(self.company, safe="")
        self.base_url = ODATA_BASE_TMPL.format(
            tenant=self.tenant, env=self.environment, company=company_enc
        )

    # ------------------------------------------------------------------ auth
    def _get_token(self) -> str:
        if self._token and time.time() < self._token_expiry - 60:
            return self._token

        url = TOKEN_URL_TMPL.format(tenant=self.tenant)
        data = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scope": self.scope,
        }
        resp = requests.post(url, data=data, timeout=30)
        if resp.status_code != 200:
            raise RuntimeError(
                f"Echec de l'authentification OAuth2 ({resp.status_code}) : {resp.text}"
            )
        payload = resp.json()
        self._token = payload["access_token"]
        self._token_expiry = time.time() + int(payload.get("expires_in", 3600))
        return self._token

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self._get_token()}",
            "Accept": "application/json",
        }

    # --------------------------------------------------------------- fetch
    def fetch_service(
        self,
        service_name: str,
        select: Optional[List[str]] = None,
        odata_filter: Optional[str] = None,
        top: Optional[int] = None,
        page_size: int = 5000,
    ) -> List[dict]:
        """Lit un service OData complet en gerant la pagination (@odata.nextLink).

        service_name : nom du service web publie dans BC.
        select       : liste de champs ($select) pour limiter le volume.
        odata_filter : expression $filter OData (ex "VAT_Date ge 2026-01-01").
        top          : limite totale d'enregistrements (utile pour tester).
        """
        params = {"$count": "true"}
        if select:
            params["$select"] = ",".join(select)
        if odata_filter:
            params["$filter"] = odata_filter
        params["$top"] = str(min(page_size, top) if top else page_size)

        url = f"{self.base_url}/{service_name}"
        records: List[dict] = []
        next_url: Optional[str] = url
        next_params: Optional[dict] = params

        while next_url:
            resp = requests.get(
                next_url, headers=self._headers(), params=next_params, timeout=120
            )
            if resp.status_code != 200:
                raise RuntimeError(
                    f"Erreur OData sur '{service_name}' ({resp.status_code}) : {resp.text[:500]}"
                )
            body = resp.json()
            batch = body.get("value", [])
            records.extend(batch)

            if top and len(records) >= top:
                return records[:top]

            # nextLink contient deja tous les parametres -> on ne les repasse pas
            next_url = body.get("@odata.nextLink")
            next_params = None

        return records

    def probe(self, service_name: str) -> List[str]:
        """Renvoie la liste des champs reels d'un service (1 enregistrement).

        Tres utile pour verifier/ajuster les noms de champs dans config.py.
        """
        rows = self.fetch_service(service_name, top=1)
        return sorted(rows[0].keys()) if rows else []


def _require_env(name: str) -> str:
    val = os.getenv(name)
    if not val:
        raise RuntimeError(
            f"Variable d'environnement manquante : {name}. "
            f"Copie .env.example en .env et renseigne-la."
        )
    return val


def build_period_filter(field_name: str, date_from: str, date_to: str) -> str:
    """Construit un $filter OData sur un champ date (bornes incluses)."""
    return f"{field_name} ge {date_from} and {field_name} le {date_to}"
