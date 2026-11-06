"""JobSearchAIAgentByAnish1989 Knowledge Base (RAG) service.

Based on the CyberQuest knowledge-base service. The Django website is the only caller.
It authenticates with the shared X-Service-Key header and tells us:
  * X-User-Role: "user" or "admin"
  * X-Owner:     whose private knowledge base to use, e.g. "c12" (one per user)
A user only ever sees their own documents plus the shared ones.
"""
import hmac
import json
import re

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from . import llm, store
from .config import ROLES, SERVICE_KEY, SHARED_OWNER, ModelConfig, load_model_config, public_view, save_model_config


class UTF8JSONResponse(JSONResponse):
    media_type = "application/json; charset=utf-8"


app = FastAPI(title="JobSearch Knowledge Base (RAG)", default_response_class=UTF8JSONResponse)

OWNER_RE = re.compile(r"^c\d{1,10}$")
NOT_FOUND_MSG = "I couldn't find this in the knowledge base."

RULES = (
    "You are the job-search assistant of JobSearchAIAgentByAnish1989, helping one person find work in "
    "Auckland, New Zealand. Use ONLY the numbered context below; never invent facts. "
    "Never invent employers, job titles, dates, qualifications, references or experience for the person. "
    "If something is not in the context, say so. Use simple, clear English unless the user writes in another language."
)


@app.on_event("startup")
def load_starter_knowledge() -> None:
    """First start: load the bundled job-search tips so questions work before anyone uploads."""
    added = store.seed_if_empty()
    if added:
        print(f"JobSearch KB: loaded the starter knowledge file ({added} chunks).")


# ---------- auth ----------
class Caller(BaseModel):
    role: str
    owner: str


def caller(
    x_service_key: str = Header(""),
    x_user_role: str = Header("user"),
    x_owner: str = Header(""),
) -> Caller:
    if not hmac.compare_digest(x_service_key.encode(), SERVICE_KEY.encode()):
        raise HTTPException(401, "Invalid service key")
    if x_user_role not in ROLES:
        raise HTTPException(403, "Unknown role")
    if not OWNER_RE.match(x_owner):
        raise HTTPException(400, "Missing or invalid owner")
    return Caller(role=x_user_role, owner=x_owner)


def need_admin(who: Caller) -> None:
    if who.role != "admin":
        raise HTTPException(403, "Only the admin can do this")


# ---------- helpers ----------
def build_context(hits: list[dict]) -> str:
    return "\n\n".join(f"[{i}] ({h['title']})\n{h['text']}" for i, h in enumerate(hits, 1))


def sources_of(hits: list[dict]) -> list[dict]:
    return [
        {"n": i, "title": h["title"], "doc_id": h["doc_id"], "score": h["score"], "shared": h["shared"],
         "snippet": h["text"][:160]}
        for i, h in enumerate(hits, 1)
    ]


def ask_model(system: str, user: str, **kw) -> str:
    try:
        return llm.chat([{"role": "system", "content": system}, {"role": "user", "content": user}], **kw)
    except Exception as e:  # network down, wrong model id, bad key ...
        raise HTTPException(502, f"Model call failed: {type(e).__name__}: {e}")


# ---------- schemas ----------
class AskReq(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    top_k: int = Field(5, ge=1, le=10)


class InterviewReq(BaseModel):
    topic: str = Field(min_length=1, max_length=300)
    count: int = Field(5, ge=1, le=15)
    top_k: int = Field(6, ge=1, le=12)


class ModelUpdate(BaseModel):
    display_name: str | None = None
    base_url: str | None = None
    model_id: str | None = None
    api_key: str | None = None  # omit/null = keep the current key
    temperature: float | None = None
    max_tokens: int | None = None
    timeout: int | None = None


# ---------- routes ----------
@app.get("/health")
def health():
    return {"ok": True}


@app.post("/v1/ask")
def ask(req: AskReq, who: Caller = Depends(caller)):
    hits = store.search(who.owner, req.question, req.top_k)
    if not hits:
        return {"answer": NOT_FOUND_MSG, "sources": []}
    system = RULES + (
        " Answer the question from the context and cite sources like [1] [2]. "
        "If the context is not enough, say you can't find it in the knowledge base."
    )
    answer = ask_model(system, f"Context:\n{build_context(hits)}\n\nQuestion: {req.question}")
    return {"answer": answer, "sources": sources_of(hits)}


@app.post("/v1/interview-questions")
def interview_questions(req: InterviewReq, who: Caller = Depends(caller)):
    """Practice interview questions with a short honest tip, written from the person's documents."""
    hits = store.search(who.owner, req.topic, req.top_k)
    if not hits:
        raise HTTPException(404, "No relevant material in the knowledge base; upload some first")
    system = RULES + (
        f" Write {req.count} likely job-interview questions for the topic, based on the context. "
        "For each, give a short tip on how to answer truthfully using only facts in the context. "
        'Output ONLY a JSON array, no other text. Each item: {"question": str, "tip": str}.'
    )
    raw = ask_model(system, f"Context:\n{build_context(hits)}\n\nTopic: {req.topic}", max_tokens=3000)
    try:
        items = json.loads(raw[raw.index("["): raw.rindex("]") + 1])
        return {"questions": items, "parsed": True, "sources": sources_of(hits)}
    except ValueError:
        return {"raw": raw, "parsed": False, "sources": sources_of(hits)}


@app.get("/v1/documents")
def documents(who: Caller = Depends(caller)):
    return {"documents": store.list_documents(who.owner)}


@app.post("/v1/documents")
async def upload_document(
    file: UploadFile = File(...),
    title: str = Form(""),
    tags: str = Form(""),
    shared: str = Form("0"),
    who: Caller = Depends(caller),
):
    owner = who.owner
    if shared == "1":
        need_admin(who)
        owner = SHARED_OWNER
    data = await file.read()
    if len(data) > 20 * 1024 * 1024:
        raise HTTPException(413, "File too large (20 MB max)")
    try:
        text = store.extract_text(file.filename or "", data)
        doc_id, n = store.add_document(owner, title or file.filename or "untitled", text, tags)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"doc_id": doc_id, "chunks": n, "shared": owner == SHARED_OWNER}


@app.delete("/v1/documents/{doc_id}")
def delete_document(doc_id: str, who: Caller = Depends(caller)):
    owner = store.owner_of(doc_id)
    if owner is None:
        raise HTTPException(404, "Document not found")
    if owner == SHARED_OWNER:
        need_admin(who)
    elif owner != who.owner:
        raise HTTPException(404, "Document not found")  # never reveal other people's documents
    store.delete_document(doc_id)
    return {"deleted": doc_id}


@app.delete("/v1/owner")
def delete_owner(who: Caller = Depends(caller)):
    """Remove all private documents of the owner (admin only, when a user is deleted)."""
    need_admin(who)
    store.delete_owner(who.owner)
    return {"deleted_owner": who.owner}


# ---------- admin only: AI model settings ----------
@app.get("/v1/admin/model")
def get_model(who: Caller = Depends(caller)):
    need_admin(who)
    return public_view(load_model_config())


@app.put("/v1/admin/model")
def put_model(req: ModelUpdate, who: Caller = Depends(caller)):
    need_admin(who)
    cfg = load_model_config()
    changes = {k: v for k, v in req.model_dump().items() if v not in (None, "")}
    save_model_config(ModelConfig(**{**cfg.model_dump(), **changes}))
    return public_view(load_model_config())


@app.post("/v1/admin/model/test")
def test_model(who: Caller = Depends(caller)):
    need_admin(who)
    reply = ask_model("You are a connectivity test.", "Reply with the single word: pong", max_tokens=20)
    return {"ok": True, "reply": reply}
