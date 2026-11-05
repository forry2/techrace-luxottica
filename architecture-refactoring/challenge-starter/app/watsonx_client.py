"""
Client per IBM watsonx AI — gestisce autenticazione IAM e chiamate al modello.
"""

import os
import requests
from typing import Optional

IAM_TOKEN_URL = "https://iam.cloud.ibm.com/identity/token"


def get_iam_token(api_key: str) -> str:
    """Ottiene un token IAM da IBM Cloud usando l'API key."""
    response = requests.post(
        IAM_TOKEN_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "grant_type": "urn:ibm:params:oauth:grant-type:apikey",
            "apikey": api_key,
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json()["access_token"]


class WatsonxClient:
    """Client per interagire con l'API watsonx AI."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        project_id: Optional[str] = None,
        url: Optional[str] = None,
        model_id: Optional[str] = None,
    ):
        self.api_key = api_key or os.environ["WATSONX_API_KEY"]
        self.project_id = project_id or os.environ["WATSONX_PROJECT_ID"]
        self.url = (url or os.environ.get("WATSONX_URL", "https://us-south.ml.cloud.ibm.com")).rstrip("/")
        self.model_id = model_id or os.environ.get("WATSONX_MODEL_ID", "openai/gpt-oss-120b")
        self._token: Optional[str] = None

    def _ensure_token(self) -> str:
        if not self._token:
            self._token = get_iam_token(self.api_key)
        return self._token

    def chat(self, messages: list, system_prompt: Optional[str] = None) -> str:
        """
        Invia una lista di messaggi al modello e restituisce la risposta testuale.

        Args:
            messages: Lista di dict {"role": "user"|"assistant", "content": "..."}
            system_prompt: Prompt di sistema opzionale.

        Returns:
            Testo della risposta del modello.
        """
        token = self._ensure_token()

        payload_messages = []
        if system_prompt:
            payload_messages.append({"role": "system", "content": system_prompt})
        payload_messages.extend(messages)

        endpoint = f"{self.url}/ml/v1/text/chat?version=2024-05-31"
        payload = {
            "model_id": self.model_id,
            "project_id": self.project_id,
            "messages": payload_messages,
            "parameters": {
                "max_new_tokens": 1024,
                "temperature": 0.7,
            },
        }

        try:
            response = requests.post(
                endpoint,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=180,
            )
            if response.status_code == 401:
                self._token = get_iam_token(self.api_key)
                response = requests.post(
                    endpoint,
                    headers={
                        "Authorization": f"Bearer {self._token}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                    timeout=180,
                )
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise RuntimeError(
                f"Errore watsonx API: {exc.response.status_code} — {exc.response.text}"
            ) from exc

        data = response.json()
        return data["choices"][0]["message"]["content"]
