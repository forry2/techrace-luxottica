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

    def _call(self, payload_messages: list, tools: Optional[list] = None) -> dict:
        """
        Esegue una singola chiamata HTTP all'API watsonx e restituisce il dict ``message``
        del primo ``choice``. Gestisce il refresh automatico del token 401.
        """
        token = self._ensure_token()
        endpoint = f"{self.url}/ml/v1/text/chat?version=2024-05-31"
        payload: dict = {
            "model_id": self.model_id,
            "project_id": self.project_id,
            "messages": payload_messages,
            "parameters": {
                "max_new_tokens": 1024,
                "temperature": 0.7,
            },
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        def _do_request(auth_token: str):
            return requests.post(
                endpoint,
                headers={
                    "Authorization": f"Bearer {auth_token}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=180,
            )

        response = _do_request(token)
        if response.status_code == 401:
            self._token = get_iam_token(self.api_key)
            response = _do_request(self._token)
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise RuntimeError(
                f"Errore watsonx API: {exc.response.status_code} — {exc.response.text}"
            ) from exc

        data = response.json()
        return data["choices"][0]["message"]

    def chat(self, messages: list, system_prompt: Optional[str] = None) -> str:
        """
        Invia una lista di messaggi al modello e restituisce la risposta testuale.

        Args:
            messages: Lista di dict {"role": "user"|"assistant", "content": "..."}
            system_prompt: Prompt di sistema opzionale.

        Returns:
            Testo della risposta del modello.
        """
        payload_messages = []
        if system_prompt:
            payload_messages.append({"role": "system", "content": system_prompt})
        payload_messages.extend(messages)
        return self._call(payload_messages)["content"]

    def chat_with_tools(
        self,
        messages: list,
        tools: list,
        system_prompt: Optional[str] = None,
    ) -> dict:
        """
        Invia messaggi al modello con definizioni di tool (function-calling).

        Returns:
            Il dict ``message`` del modello (può contenere ``tool_calls`` oppure ``content``).
        """
        payload_messages = []
        if system_prompt:
            payload_messages.append({"role": "system", "content": system_prompt})
        payload_messages.extend(messages)
        return self._call(payload_messages, tools=tools)
