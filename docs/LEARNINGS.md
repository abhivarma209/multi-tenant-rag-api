# Learnings — Multi-Tenant RAG API

Concepts covered while building Project 2 from scratch.

---

## 1. What is RAG — Complete Understanding

RAG (Retrieval-Augmented Generation) exists for three distinct reasons:

1. **Context limits** — documents too large to fit in one prompt
2. **Precision** — only relevant chunks sent, not entire document.
   Too much irrelevant context degrades model performance
   ("lost in the middle" problem)
3. **Knowledge freshness** — inject private or real-time data
   the model was never trained on

### The complete RAG pipeline
```
Document → Extract text → Chunk → Embed → Store in vector DB
Question → Embed → Semantic search → Retrieve top K chunks
Chunks + Question → LLM → Grounded answer
```

---

## 2. Embeddings — What They Actually Are

An embedding is a list of numbers (vector) representing the *meaning*
of text. Similar meanings produce similar vectors.

```python
"The invoice total is $500"
→ [0.23, -0.87, 0.12, 0.45, ...]  (1536 numbers)

"The bill amount is five hundred dollars"
→ [0.24, -0.85, 0.13, 0.44, ...]  (very similar — same meaning)

"The cat sat on the mat"
→ [0.91, 0.23, -0.67, 0.02, ...]  (very different meaning)
```

### Why not Postgres full-text search?
Full-text search matches exact words.
Semantic search matches meaning — finds "invoice total: $500"
when you search "how much do I owe" even with zero word overlap.

---

## 3. Chunking Strategy

### The tradeoff
- Too large: retrieval imprecise, noise alongside signal, context limit risk
- Too small: loses context, incomplete thoughts embed poorly
- Sweet spot: 500-1000 tokens with 100-200 token overlap

### Why overlap matters
Without overlap, a sentence split across two chunks loses context
at the boundary. Overlap means chunk endings repeat at the next
chunk's start — no sentence is ever fully cut.

```
Chunk 1: tokens 1   → 800
Chunk 2: tokens 650 → 1450   ← 150 token overlap with chunk 1
Chunk 3: tokens 1300 → 2100  ← 150 token overlap with chunk 2
```

### RecursiveCharacterTextSplitter split order
1. Paragraph breaks (\n\n)
2. Newlines (\n)
3. Sentences (. )
4. Words ( )
5. Characters (last resort)

Never cuts mid-paragraph unless absolutely necessary.

---

## 4. Tenant Isolation Pattern

### Metadata filtering — the production standard
Every chunk stored with tenant_id metadata.
Every search filtered by tenant_id.

```python
# storing
metadatas=[{"tenant_id": str(tenant_id), "filename": "doc.pdf"}]

# searching — isolation enforced here
where={"tenant_id": str(tenant_id)}
```

One misconfigured query without the filter = data breach.
Add it as a non-optional parameter, never default.

### Why one collection over per-tenant collections
- Scales to thousands of tenants without management overhead
- Simpler deployment
- Metadata filtering is just as secure when enforced consistently

---

## 5. SQLAlchemy ORM Patterns

### Column() vs type annotations
SQLAlchemy ORM uses Column() definitions, not Pydantic-style annotations:

```python
# WRONG (Pydantic style)
name: str = default("value")

# CORRECT (SQLAlchemy)
name = Column(String, nullable=False)
```

### Default values — no parentheses
```python
# WRONG — evaluates once at import, all rows get same timestamp
created_at = Column(DateTime, default=datetime.utcnow())

# CORRECT — called fresh on each insert
created_at = Column(DateTime, default=datetime.utcnow)
```

### Always index filter columns
```python
api_key  = Column(String, unique=True, index=True)  # auth lookup
tenant_id = Column(UUID, ForeignKey("tenants.id"), index=True)  # every query
```

Without index: O(n) full table scan on every auth check.
With index: O(log n) lookup regardless of table size.

### db.add() is required
```python
# WRONG — object not tracked, commit saves nothing
Document(id=doc_id, filename="doc.pdf")
db.commit()

# CORRECT
document = Document(id=doc_id, filename="doc.pdf")
db.add(document)    # tell SQLAlchemy to track this
db.commit()         # now it saves
```

### yield in FastAPI dependencies
```python
def get_db():
    db = SessionLocal()
    try:
        yield db       # request runs here
    finally:
        db.close()     # always runs after response sent
```

Everything after yield is cleanup. FastAPI calls it automatically.
Without yield, you'd need try/finally everywhere you use the database.

---

## 6. API Key Security Patterns

### Always 401, never 404 for auth failures
404 leaks existence — attacker knows the key format was valid.
401 always — never confirm whether a key exists or not.

### Generic error messages
```python
# WRONG — leaks information
detail="Tenant not found"

# CORRECT — reveals nothing
detail="Invalid API key"
```

### API key generation
```python
api_key = f"rag-{uuid.uuid4().hex}"
```
Prefix (rag-) makes keys identifiable in logs.
UUID hex gives 32 random characters — 128 bits of entropy.

---

## 7. Docker Compose Patterns

### depends_on with health checks
```yaml
api:
  depends_on:
    postgres:
      condition: service_healthy
    chromadb:
      condition: service_healthy
```

Without this, API starts before databases are ready and crashes.
Health checks are what make depends_on actually work.

### Named volumes for persistence
```yaml
volumes:
  postgres_data:   # survives docker compose down
  chroma_data:
```

Safe commands:
- `docker compose down` — stops containers, keeps volumes
- `docker compose up` — restores data from volumes
- `docker compose down -v` — DESTROYS volumes, never in production

---

## 8. Batching API Calls

### Embed all chunks in one call
```python
# WRONG — N API calls, N × latency
for chunk in chunks:
    embed(chunk)

# CORRECT — 1 API call regardless of chunk count
embeddings = embed_texts(chunks)  # list of all chunks
```

Benefits: 1 network round trip, stays under rate limits,
significantly faster for large documents.

---

## 9. Grounding — Preventing Hallucination

### The critical system prompt instruction
```
"Answer ONLY from the provided context.
If the answer is not present, say:
'I couldn't find this information in your documents.'"
```

### Why "I don't know" beats hallucination in RAG
User uploads HR policy. Asks about sick days.
Model hallucinates "15 days" confidently.
Employee acts on wrong information.
Company blames your product. Trust destroyed.

Honest "I don't know" → user asks HR directly → no harm.
In RAG, a confident wrong answer is worse than no answer.

### Early return on empty retrieval
```python
if not chunks:
    return {"answer": "I couldn't find this...", "sources": []}
```

Never call the LLM with no context — it will hallucinate.

---

## 10. Production Patterns Applied

- Tenant isolation enforced at query level, not application level
- db.rollback() on upload failure — consistent state always
- Structured logging per request with tenant name and chunk count
- File validation before processing (415, 413, 422)
- Health check for orchestration (Kubernetes, Docker Compose depends_on)
- Named volumes for data persistence
- .env for secrets, never in code or image

---

## 11. RAGAS — Evaluating RAG Pipelines

RAGAS answers: "How good is my RAG system, objectively?"
Without it you're guessing. With it you have numbers.

### What RAGAS measures

**Faithfulness** — Did the answer come from the retrieved chunks?
Checks whether every claim in the answer is traceable to the context.

```
Context:  "The invoice total is $30,798.89"
Answer:   "The total is $30,798.89. Payment due in 30 days."
                                     ↑ not in context → score drops
```

Score 1.0 = fully grounded. Score 0.0 = fully hallucinated.
Low faithfulness → fix your system prompt or lower temperature.

**Answer Relevancy** — Does the answer address the question?
Re-embeds the answer and measures semantic similarity to the question.
A vague or off-topic answer scores low even if factually correct.

```
Question: "What is the GST rate?"
Answer:   "The invoice was issued by CloudStack Solutions."
          ↑ True, but irrelevant → low answer relevancy
```

Low answer relevancy → fix your chunking or retrieval (wrong chunks returned).

**Context Recall** (not run yet) — Did the retriever fetch the right chunks?
Needs a full-sentence ground truth, not just a value. Diagnoses retrieval
failures separately from generation failures.

### The debugging matrix

| Problem | Faithfulness | Answer Relevancy |
|---------|-------------|-----------------|
| LLM hallucinating | Low | Normal |
| Bad retrieval | Normal | Low |
| Both broken | Low | Low |

### How RAGAS scores — it calls the LLM to judge

RAGAS uses GPT internally to evaluate your answers. It's LLM-as-judge.
5 test cases costs ~$0.01. Worth knowing before running in a loop.

### What the eval loop must collect

RAGAS needs four parallel lists:

```python
questions     = []   # the question string
answers       = []   # result["answer"]  — just the string, not the full dict
contexts      = []   # [chunk["text"] for chunk in chunks] — list of lists
ground_truths = []   # expected answer string
```

The key mistake: `generate_answer` returns `{"answer": ..., "sources": ...}`.
You need `result["answer"]`, not `result` itself.
And contexts must be captured from `search_chunks` output before passing to generate.

```python
for case in TEST_CASES:
    chunks = search_chunks(case["question"], tenant_id)
    result = generate_answer(case["question"], chunks)

    questions.append(case["question"])
    answers.append(result["answer"])                          # string, not dict
    contexts.append([chunk["text"] for chunk in chunks])      # list[str] per question
    ground_truths.append(case["ground_truth"])
```

---

## 12. Docker Volume Mount Bugs

### Always verify persist_path matches volume mount

ChromaDB logs its persist path on startup:
```
persist_path: "/data"
```

If your docker-compose mounts to a different path, data is written
to the container filesystem and lost on every restart:

```yaml
# WRONG — volume mounted at /chroma/chroma but chromadb writes to /data
volumes:
  - chroma_data:/chroma/chroma

# CORRECT — matches chromadb's actual persist_path
volumes:
  - chroma_data:/data
```

Symptom: Postgres has document records (chunk_count > 0) but ChromaDB
collection returns 0 results. The document metadata survived (Postgres
has its own volume) but the vectors didn't (written outside the volume).

### How to verify

```bash
# check where chromadb is actually writing
docker exec <chromadb-container> sh -c "ls /data/"
docker exec <chromadb-container> sh -c "ls /chroma/chroma/"

# check collection count
python -c "
from database import get_chroma_client, get_collection
col = get_collection(get_chroma_client())
print(col.count())
"
```

---

## 13. Docker Health Check — Know Your Image's Tools

Health checks fail silently if the tool doesn't exist in the container.
The container shows "unhealthy" but the real error is in inspect logs.

```bash
docker inspect <container> --format='{{range .State.Health.Log}}{{.Output}}{{end}}'
```

ChromaDB's image has neither `python`, `curl`, nor `wget` in PATH.
Use bash's built-in TCP redirect instead:

```yaml
healthcheck:
  test: ["CMD-SHELL", "bash -c '</dev/tcp/localhost/8000'"]
```

This opens a TCP connection to port 8000. Exit 0 = port accepting connections.
No external tool needed — bash built-in only.

### How to find what tools exist in an image

```bash
docker exec <container> sh -c "ls /usr/bin/"
```
