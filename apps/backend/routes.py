from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from services.session import SessionContext, require_session
from services.agent_runs import enqueue_agent_run
from services.chat import ChatRequest, chat_stream
from services.conversations import (
    create_conversation,
    get_conversation,
    list_conversations,
)
from services.events import stream_run_events
from services.artifacts import list_for_run, get_artifact

router = APIRouter(prefix="/api")


class RunSubmitRequest(BaseModel):
    prompt: str


class CreateConversationRequest(BaseModel):
    title: str | None = None


@router.get("/me")
def me(request: Request, response: Response) -> dict:
    session = require_session(request, response)
    return session.model_dump()


@router.get("/conversations")
def get_conversations(session: SessionContext = Depends(require_session)) -> list[dict]:
    return list_conversations(session.session_id)


@router.post("/conversations")
def post_conversation(
    payload: CreateConversationRequest,
    session: SessionContext = Depends(require_session),
) -> dict:
    cid = create_conversation(session.session_id, payload.title)
    return {"conversation_id": cid}


@router.get("/conversations/{conversation_id}")
def get_conversation_route(
    conversation_id: str,
    session: SessionContext = Depends(require_session),
) -> dict:
    return get_conversation(conversation_id, session.session_id)


@router.post("/runs")
def submit_run(
    payload: RunSubmitRequest,
    session: SessionContext = Depends(require_session),
) -> dict:
    agent_run_id = enqueue_agent_run(session, payload.prompt)
    return {"agent_run_id": agent_run_id, "status": "queued"}


@router.post("/chat")
def chat(
    payload: ChatRequest,
    session: SessionContext = Depends(require_session),
) -> StreamingResponse:
    return StreamingResponse(
        chat_stream(payload, session),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/runs/{run_id}/events")
async def run_events(run_id: str, request: Request) -> StreamingResponse:
    return await stream_run_events(request, run_id)


@router.get("/runs/{run_id}/artifacts")
def list_artifacts(run_id: str, session: SessionContext = Depends(require_session)) -> list:
    refs = list_for_run(run_id, session.session_id)
    return [
        {
            "artifact_id": r.artifact_id,
            "agent_run_id": r.run_id,
            "filename": r.filename,
            "content_type": r.content_type,
            "size_bytes": r.size,
        }
        for r in refs
    ]


@router.get("/runs/{run_id}/artifacts/{artifact_id}")
def download_artifact(
    run_id: str,
    artifact_id: str,
    session: SessionContext = Depends(require_session),
):
    result = get_artifact(run_id, artifact_id, session.session_id)
    if result is None:
        raise HTTPException(status_code=404, detail="artifact not found")

    ref, data = result
    safe_name = Path(ref.filename).name
    return Response(
        content=data,
        media_type=ref.content_type,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(safe_name)}"},
    )
