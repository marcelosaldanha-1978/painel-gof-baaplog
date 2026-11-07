# -*- coding: utf-8 -*-
"""
gof_google.py (v1, 07nov2026) — token de acesso da conta de serviço SÓ DE LEITURA (D14, PLANO v2.4).

A chave vem do segredo `GOOGLE_SA_JSON` (conteúdo do JSON) ou, localmente, de `GOOGLE_SA_KEY_FILE` (caminho).
Escopos: somente leitura de planilhas e do Drive. Nunca imprime nem grava a chave ou o token.
"""
import json
import os

ESCOPOS = ("https://www.googleapis.com/auth/spreadsheets.readonly", "https://www.googleapis.com/auth/drive.readonly")


def credencial():
    import google.auth.transport.requests
    from google.oauth2 import service_account

    bruto = os.environ.get("GOOGLE_SA_JSON", "").strip()
    if bruto:
        info = json.loads(bruto)
        cred = service_account.Credentials.from_service_account_info(info, scopes=ESCOPOS)
    else:
        arq = os.environ.get("GOOGLE_SA_KEY_FILE", "").strip()
        if not arq:
            raise RuntimeError("GOOGLE_SA_JSON (ou GOOGLE_SA_KEY_FILE) ausente")
        cred = service_account.Credentials.from_service_account_file(arq, scopes=ESCOPOS)
    cred.refresh(google.auth.transport.requests.Request())
    return cred


def token():
    return credencial().token


def conta():
    """E-mail da conta (não é segredo); serve para o log dizer com que conta leu."""
    bruto = os.environ.get("GOOGLE_SA_JSON", "").strip()
    if bruto:
        return json.loads(bruto).get("client_email", "?")
    arq = os.environ.get("GOOGLE_SA_KEY_FILE", "").strip()
    return json.load(open(arq, encoding="utf-8")).get("client_email", "?") if arq else "?"
