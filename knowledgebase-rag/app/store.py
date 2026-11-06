"""Knowledge base: extract -> chunk -> embed -> store (Chroma) -> search.

From CyberQuest, with one change: every chunk has an "owner".
  * "c<id>"  = one user's private documents (only that user's questions can find them)
  * "shared" = documents the admin shares with everyone
"""
import io
import re
import uuid

import chromadb
from chromadb.utils import embedding_functions
from pypdf import PdfReader

from .config import DATA_DIR, EMBED_MODEL, MIN_SCORE, SEED_FILE, SHARED_OWNER

_client = chromadb.PersistentClient(path=str(DATA_DIR / "chroma"))
_embed = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=EMBED_MODEL)
_col = _client.get_or_create_collection(
    "jobsearch_kb", embedding_function=_embed, metadata={"hnsw:space": "cosine"}
)


def extract_text(filename: str, data: bytes) -> str:
    name = filename.lower()
    if name.endswith(".pdf"):
        reader = PdfReader(io.BytesIO(data))
        return "\n\n".join((page.extract_text() or "") for page in reader.pages)
    if name.endswith((".txt", ".md")):
        return data.decode("utf-8", errors="ignore")
    raise ValueError("Only .pdf, .txt and .md files are supported")


def chunk_text(text: str, size: int = 800, overlap: int = 120) -> list[str]:
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks, buf = [], ""
    for p in paras:
        if len(buf) + len(p) + 1 <= size:
            buf = f"{buf}\n{p}" if buf else p
            continue
        if buf:
            chunks.append(buf)
        while len(p) > size:  # very long paragraph: hard-split with overlap
            chunks.append(p[:size])
            p = p[size - overlap:]
        buf = p
    if buf:
        chunks.append(buf)
    return chunks


def _visible(owner: str) -> dict:
    """Chroma filter: this owner's documents plus the shared ones."""
    return {"owner": {"$in": [owner, SHARED_OWNER]}}


KINDS = {"cv", "cover_letter", "other"}


def add_document(owner: str, title: str, text: str, tags: str = "", kind: str = "other") -> tuple[str, int]:
    chunks = chunk_text(text)
    if not chunks:
        raise ValueError("No readable text found in the document")
    doc_id = uuid.uuid4().hex[:12]
    _col.add(
        ids=[f"{doc_id}-{i}" for i in range(len(chunks))],
        documents=chunks,
        metadatas=[
            {"doc_id": doc_id, "owner": owner, "title": title, "tags": tags, "kind": kind if kind in KINDS else "other",
             "chunk": i}
            for i in range(len(chunks))
        ],
    )
    return doc_id, len(chunks)


def list_documents(owner: str) -> list[dict]:
    metas = _col.get(where=_visible(owner), include=["metadatas"])["metadatas"] or []
    docs: dict[str, dict] = {}
    for m in metas:
        d = docs.setdefault(
            m["doc_id"],
            {"doc_id": m["doc_id"], "title": m["title"], "tags": m["tags"], "chunks": 0,
             "kind": m.get("kind", "other"), "shared": m["owner"] == SHARED_OWNER},
        )
        d["chunks"] += 1
    return sorted(docs.values(), key=lambda d: (not d["shared"], d["title"].lower()))


def owner_of(doc_id: str) -> str | None:
    got = _col.get(where={"doc_id": doc_id}, limit=1, include=["metadatas"])["metadatas"] or []
    return got[0]["owner"] if got else None


def delete_document(doc_id: str) -> None:
    _col.delete(where={"doc_id": doc_id})


def delete_owner(owner: str) -> None:
    """Remove every private document of one user (used when a user is deleted)."""
    if owner != SHARED_OWNER:
        _col.delete(where={"owner": owner})


def search(owner: str, query: str, k: int = 5, include_shared: bool = True, kinds: list[str] | None = None) -> list[dict]:
    """Best matching chunks. include_shared=False: only this person's own documents (used for CV writing,
    so shared tips are never treated as facts about the person). kinds: only these document kinds."""
    where = _visible(owner) if include_shared else {"owner": owner}
    if kinds:
        where = {"$and": [where, {"kind": {"$in": kinds}}]}
    visible = _col.get(where=where, include=[])["ids"]
    if not visible:
        return []
    res = _col.query(query_texts=[query], n_results=min(k, len(visible)), where=where)
    hits = []
    for text, meta, dist in zip(res["documents"][0], res["metadatas"][0], res["distances"][0]):
        score = round(1 - dist, 3)
        if score >= MIN_SCORE:
            hits.append({"text": text, "title": meta["title"], "doc_id": meta["doc_id"], "score": score,
                         "shared": meta["owner"] == SHARED_OWNER, "kind": meta.get("kind", "other")})
    return hits


def seed_if_empty() -> int:
    """Load the bundled job-search tips into the SHARED part when the knowledge base is empty.

    Returns the number of chunks added (0 when there was already something, or no seed file).
    """
    if _col.count() > 0 or not SEED_FILE.is_file():
        return 0
    text = SEED_FILE.read_text("utf-8", errors="ignore")
    _doc_id, chunks = add_document(SHARED_OWNER, "Job search in Auckland - starter tips", text, "starter, nz, cv")
    return chunks
