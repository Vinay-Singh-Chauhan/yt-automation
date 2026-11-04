import base64
import binascii
import json
import logging

import requests
from fastapi import FastAPI, HTTPException, Request, Response
from google.auth import default
from google.auth.transport.requests import AuthorizedSession

from app.config import Settings
from app.models import RunRequest

logging.basicConfig(level=logging.INFO)
LOGGER = logging.getLogger(__name__)
app = FastAPI(title="YouTube Shorts Pipeline")


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


def _decode_pubsub(body: dict) -> tuple[dict, str | None]:
    try:
        message = body["message"]
        encoded = message["data"]
        payload = json.loads(base64.b64decode(encoded, validate=True))
    except (KeyError, ValueError, TypeError, binascii.Error) as exc:
        raise HTTPException(status_code=400, detail="Invalid Pub/Sub message") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Pub/Sub data must be a JSON object")
    return payload, message.get("messageId")


def _start_workflow(payload: dict, message_id: str | None) -> None:
    settings = Settings.from_env()
    if not settings.project_id or not settings.workflow_name:
        raise RuntimeError("GOOGLE_CLOUD_PROJECT and WORKFLOW_NAME must be configured")
    credentials, _ = default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    session = AuthorizedSession(credentials)
    name = (
        f"projects/{settings.project_id}/locations/{settings.region}/"
        f"workflows/{settings.workflow_name}/executions"
    )
    response = session.post(
        f"https://workflowexecutions.googleapis.com/v1/{name}",
        json={"argument": json.dumps({"payload": payload, "message_id": message_id})},
        timeout=15,
    )
    if not response.ok:
        raise RuntimeError(f"Could not start workflow ({response.status_code}): {response.text[:1000]}")


@app.post("/pubsub")
async def receive_pubsub(request: Request):
    try:
        body = await request.json()
    except (ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Request body must be JSON") from exc
    payload, message_id = _decode_pubsub(body)
    try:
        validated = RunRequest.model_validate(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        _start_workflow(validated.model_dump(exclude_none=True), message_id)
    except (requests.RequestException, RuntimeError) as exc:
        LOGGER.exception("Failed to start pipeline workflow")
        raise HTTPException(status_code=503, detail="Unable to start pipeline workflow") from exc
    return Response(status_code=204)
