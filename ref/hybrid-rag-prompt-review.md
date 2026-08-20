# รีวิวพรอมต์ Hybrid RAG

> **ที่มา:** [ChatGPT shared conversation](https://chatgpt.com/share/6a867f05-aefc-83ec-918c-bb14b0245504)  
> **สร้างเมื่อ:** 2026-08-20 11:13 (UTC+7)  
> **โมเดล:** auto  
> **ดึงข้อมูลเมื่อ:** 2026-08-20

---

## 👤 ผู้ใช้ — ข้อความที่ 1

prompt นี้เป็นไงบ้าง

You are an expert Systems Architect, AI Infrastructure Engineer, and Full-Stack Python Developer. Your task is to implement a production-ready, high-performance **Two-Stage Hybrid RAG Engine** featuring unified dual-mode execution (**Direct LCEL Pipeline** and **FastMCP Server**) along with a comprehensive, automated **Test Harness & Evaluation Benchmark Suite**.

---

##### 1. System Architecture & Technical Specifications

1. **Storage & Database Layer (PostgreSQL + pgvector):**
   - Driver: `psycopg` (v3) using `ConnectionPool` for thread-safe concurrent connections.
   - Database table: `langchain_hybrid_docs`
     - `id`: UUID (Primary Key, default `uuid_generate_v4()`)
     - `content`: TEXT NOT NULL
     - `metadata`: JSONB NOT NULL DEFAULT '{}'::jsonb
     - `embedding`: vector(1536) (using OpenAI `text-embedding-3-small`)
     - `tsv_content`: tsvector GENERATED ALWAYS AS (`to_tsvector('english', content)`) STORED
   - Required Indexes:
     - HNSW: `CREATE INDEX ... USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);`
     - Full-Text Search: `CREATE INDEX ... USING gin (tsv_content);`
     - Metadata Containment: `CREATE INDEX ... USING gin (metadata jsonb_path_ops);`

2. **Two-Stage Retrieval Pipeline:**
   - **Stage 1 (Hybrid SQL + JSONB Pre-filtering + RRF):**
     - Single parameterized SQL using CTEs for Dense Vector Search (`<=>` Cosine Distance) and Sparse Full-Text Search (`ts_rank_cd`).
     - Hard Pre-filtering applied inside both CTEs via JSONB containment (`metadata @> %s::jsonb`).
     - Session parameter: enforce `SET hnsw.ef_search = 40;` before executing vector queries.
     - Rank aggregation: Reciprocal Rank Fusion formula `1.0 / (60 + rank)` to retrieve `candidate_k` (default 10).
   - **Stage 2 (Cross-Encoder Re-ranking):**
     - Use `flashrank.Ranker` (`ms-marco-TinyBERT-L-2-v2` via ONNX Runtime on CPU).
     - Score and re-sort candidates based on pairwise cross-attention scores.
     - Return final `top_k` (default 2-3).

3. **Unified Dual-Mode Execution (`rag_engine.py`):**
   - CLI flags: `--mode direct|mcp`, `--transport stdio|sse`, `--reindex`, `--query`, `--dept`, `--doc-type`.
   - **Mode A (Direct LCEL):** LangChain Expression Language with `ChatPromptTemplate`, `ChatOpenAI(model="gpt-4o-mini", temperature=0)`, and `StrOutputParser`.
   - **Mode B (FastMCP Server):** FastMCP tool exposing `search_company_knowledge(query: str, department: Optional[str] = None, document_type: Optional[str] = None, final_k: int = 2)`.
   - **Transport Integrity:** In MCP `stdio` mode, NEVER emit stdout logs (prevents JSON-RPC corruption). All logs must route to `sys.stderr`.

---

##### 2. Test Harness & Evaluation Suite (`test_harness.py`)

Implement an automated testing and benchmarking script that measures the following:

1. **Retrieval & Hit-Rate Evaluation (Ground-Truth QA Pairs):**
   - Provide a suite of predefined test cases (Query, Expected Document IDs, Metadata Scope).
   - Evaluate and compute:
     - **Hit@K / Recall@K:** Did the correct context land in Stage 1 and Stage 2 top-k?
     - **MRR (Mean Reciprocal Rank):** Position evaluation of the relevant ground-truth chunk.
     - **Metadata Filter Precision:** Verify 0% leak of documents outside the specified JSONB filter scope.

2. **Comparative Benchmark Matrix:**
   - Run parallel evaluations across 3 strategies for the same query set:
     1. Vector-only (Dense HNSW)
     2. Hybrid without Re-ranking (HNSW + FTS + RRF)
     3. Two-Stage Hybrid + FlashRank Re-ranker
   - Output an ASCII summary table comparing **Hit Rate**, **MRR**, and **End-to-End Execution Latency (p50 / p95 in ms)**.

3. **MCP Protocol Functional Test:**
   - Programmatically spin up the FastMCP server instance and call `search_company_knowledge` tool via standard MCP client protocol calls to verify end-to-end JSON-RPC payload integrity.

---

##### 3. Deliverables Required

Generate clean, modular, typed Python code with zero placeholders:

1. **`schema.sql`**: Full DDL including extension creation, table schema, and all 3 optimized indexes.
2. **`requirements.txt`**: Minimal pinned dependencies (`langchain-core`, `langchain-openai`, `psycopg[binary,pool]`, `flashrank`, `mcp`, `tabulate`, `pytest`).
3. **`rag_engine.py`**: Complete implementation of DB Pool, Ingestion, Two-Stage Hybrid Pipeline, LCEL Runner, and FastMCP Server.
4. **`test_harness.py`**: Complete automated test runner and benchmarking suite with tabulated performance metrics.

---

## 🤖 ChatGPT — ข้อความที่ 2

โดยรวม **prompt นี้ดีมาก และค่อนข้าง production-oriented** ครับ แต่ถ้าจะเอาไปให้ coding agent ลงมือสร้างจริง ผมแนะนำปรับอีกนิด เพราะตอนนี้มีบางจุดที่ “ดูครบ” แต่ agent อาจตีความต่างกัน หรือ benchmark อาจวัดผลไม่ตรงกับสิ่งที่ต้องการ

##### จุดที่ทำได้ดีมาก

1. **Architecture ชัด**
   - PostgreSQL + pgvector
   - Dense + FTS
   - RRF
   - Cross-encoder
   - Direct / MCP
   - Test harness

   ทำให้ agent ไม่ต้องเดา architecture หลัก

2. **กำหนด SQL-level filtering ถูกทาง**
   
   การบังคับ `metadata @> ...` ในทั้ง Dense และ FTS CTE สำคัญมาก เพราะป้องกัน filter ถูกนำไปใช้หลัง retrieval จนเกิด leakage

3. **มี benchmark 3 ระดับ**
   
   อันนี้ผมชอบเป็นพิเศษ:

   `Vector → Hybrid → Hybrid + Reranker`

   เพราะจะตอบได้จริงว่าแต่ละ layer เพิ่มคุณค่าเท่าไร ไม่ใช่แค่ "ระบบทำงาน"

4. **MCP stdio integrity ระบุไว้ชัด**
   
   เรื่อง stdout/stderr เป็นรายละเอียดที่ coding agent มักพลาด แต่ prompt นี้จับไว้แล้ว

---

#### แต่มี 7 จุดที่ผมแนะนำให้แก้ก่อนส่งให้ agent

##### 1. `uuid_generate_v4()` ต้องมี extension

ใน `schema.sql` ต้องระบุ `uuid-ossp` ไม่อย่างนั้น DDL อาจรันไม่ได้

หรือเปลี่ยนไปใช้:

```sql
gen_random_uuid()
```

แล้วใช้ `pgcrypto`

ผมแนะนำ `gen_random_uuid()` เพราะเป็นแนวทางที่ง่ายกว่าใน PostgreSQL รุ่นใหม่

---

##### 2. `hnsw.ef_search` ต้องระวัง connection pool

Prompt บอกว่า

> Session parameter: enforce `SET hnsw.ef_search = 40;`

แต่ใช้ `ConnectionPool`

ต้องกำหนดให้ชัดว่า setting นี้ต้องอยู่ **ใน transaction/connection เดียวกับ vector query**

ไม่อย่างนั้น agent อาจทำ:

```python
pool.connection()
SET hnsw.ef_search = 40
```

แล้วคืน connection กลับ pool ทำให้ behavior ไม่ deterministic

ควรเขียนประมาณ:

> Every vector retrieval must execute `SET LOCAL hnsw.ef_search = 40` within the same transaction/connection that executes the HNSW query.

จะ robust กว่ามาก

---

##### 3. RRF ตอนนี้ยัง ambiguous

ตอนนี้เขียน:

> `1.0 / (60 + rank)`

ควรระบุว่าเป็น **RRF k=60** และ rank เริ่มจาก 1

เช่น:

```text
rrf_score = Σ 1 / (60 + rank)
```

และต้องบอกด้วยว่า candidate pool ของ Dense/FTS แต่ละตัวมีขนาดเท่าไร

เช่น:

```text
dense_k = candidate_k
sparse_k = candidate_k
candidate_k = 10
```

ไม่อย่างนั้น implementation แต่ละ agent อาจเลือกคนละแบบ

---

##### 4. Ground truth ต้องนิยามให้ละเอียดกว่านี้

นี่คือจุดสำคัญที่สุดของ `test_harness.py`

ตอนนี้บอกว่า:

> Expected Document IDs

แต่ต้องกำหนด schema ของ test case เช่น:

```python
{
    "query": "...",
    "expected_ids": ["uuid1", "uuid2"],
    "metadata_filter": {
        "department": "finance"
    }
}
```

และนิยาม metric ให้ชัด:

- Hit@K = มี expected ID อย่างน้อยหนึ่งตัวหรือไม่
- Recall@K = จำนวน relevant IDs ที่พบ / จำนวน relevant IDs ทั้งหมด
- MRR = reciprocal rank ของ relevant result แรก
- Filter leakage = จำนวน result ที่ metadata ไม่ตรง filter / จำนวน result ทั้งหมด

ไม่อย่างนั้น benchmark จะมีโอกาสกลายเป็น implementation-specific

---

##### 5. ควรเพิ่ม **offline benchmark mode**

ตอนนี้ test harness น่าจะต้องมี OpenAI embedding และ database จริง ซึ่งทำให้ benchmark:

- ช้า
- แพง
- reproducibility ต่ำ

ผมแนะนำเพิ่ม 2 mode:

```text
--mode integration
--mode benchmark
```

หรือ:

```text
LIVE
OFFLINE
```

โดย offline ใช้ fixture embeddings / preloaded DB เพื่อวัด retrieval algorithm โดยไม่ยิง OpenAI

จะทำให้ regression test มีประโยชน์มากขึ้น

---

##### 6. ควรแยก Retrieval กับ Generation

ตอนนี้ `rag_engine.py` มีทั้ง:

```text
Retrieval
+
LCEL
+
ChatOpenAI
+
MCP
```

ผมแนะนำ architecture เป็น:

```text
                 ┌─────────────────┐
                 │ RetrievalEngine │
                 └────────┬────────┘
                          │
              ┌───────────┴───────────┐
              │                       │
        Direct Runner             MCP Tool
              │                       │
          LCEL/RAG                FastMCP
              │
          ChatOpenAI
```

อย่างน้อยภายในไฟล์ควรแยก class:

```python
HybridRetriever
CrossEncoderReranker
RAGService
DirectRunner
MCPServer
```

เพราะอนาคตจะเอา `HybridRetriever` ไปเสียบกับ agent platform / MCP / API ได้ง่ายมาก

---

##### 7. MCP test ควรระบุ transport ให้ชัด

ตอนนี้บอก:

> standard MCP client protocol calls

ดี แต่ agent อาจเลือก implementation แตกต่างกัน

ผมจะกำหนดว่า test ต้อง:

1. start server in-process หรือ subprocess
2. establish MCP client session
3. initialize
4. list tools
5. assert `search_company_knowledge` exists
6. call tool
7. validate structured response
8. validate no stdout contamination ใน stdio
9. shutdown cleanly

โดยเฉพาะข้อ 8 นี่สำคัญมาก

---

### อีกเรื่องที่ผมอยากเพิ่มมากที่สุด

ให้ benchmark **แยก retrieval latency ออกจาก generation latency**

ไม่อย่างนั้น:

```text
p95 = PostgreSQL + FlashRank + OpenAI
```

จะตอบไม่ได้ว่า RAG engine เร็วหรือช้า

ควรวัดอย่างน้อย:

```text
DB Dense latency
DB FTS latency
RRF latency
Reranker latency
Retrieval total latency
Generation latency
End-to-end latency
```

แล้วรายงาน:

```text
                 p50       p95
Dense            xx ms     xx ms
Hybrid           xx ms     xx ms
Reranker         xx ms     xx ms
Retrieval        xx ms     xx ms
Generation       xx ms     xx ms
E2E              xx ms     xx ms
```

อันนี้จะทำให้ prompt จากแค่ **"สร้าง RAG"** กลายเป็น **"สร้าง RAG engine ที่วัด performance ได้จริง"**

---

#### และมี architectural point สำคัญอีกอย่าง

ถ้าจุดประสงค์คือเอา engine นี้เข้า ecosystem ที่กำลังทำอยู่ ผมจะ **ไม่ให้ `rag_engine.py` เป็น application เดียวที่ทำทุกอย่าง**

ให้มันเป็นประมาณนี้:

```text
RAG Engine
│
├── Storage
│   └── PostgreSQL / pgvector
│
├── Retrieval
│   ├── Dense
│   ├── Sparse
│   ├── Hybrid RRF
│   └── Reranker
│
├── Service
│   └── search_company_knowledge()
│
├── Adapters
│   ├── Direct LCEL
│   └── MCP
│
└── Evaluation
    ├── Ground Truth
    ├── Metrics
    └── Benchmark
```

แบบนี้มันจะกลายเป็น **Reusable RAG Retrieval Service** มากกว่า demo RAG

และ MCP จะเป็นเพียง adapter ตัวหนึ่ง ไม่ใช่ core ของระบบ

---

#### สรุป

ผมให้ prompt ปัจจุบันประมาณ **8.5/10**

ถ้าปรับ 7 จุดด้านบน โดยเฉพาะ:

- transaction-safe `hnsw.ef_search`
- RRF definition
- ground-truth schema
- metric definitions
- offline benchmark
- retrieval/generation separation
- MCP protocol test

จะขึ้นไปประมาณ **9.5/10 สำหรับให้ coding agent ลงมือทำ**

และที่สำคัญ ผมมองว่าแนวนี้ **เข้ากับ Agent Platform ที่กำลังวางอยู่มาก** เพราะตัวนี้ควรเป็น **RAG/Knowledge Retrieval capability** ที่ expose ผ่าน MCP ได้ ไม่ควรผูกตัวเองเป็น "MCP RAG application" ตั้งแต่ core ครับ

---

## 👤 ผู้ใช้ — ข้อความที่ 3

เยี่ยมเลย ขอภาพรวมและแนวทาง จะส่งให้ทีมจร้า

---

## 🤖 ChatGPT — ข้อความที่ 4

ได้เลยครับ แนวทางที่ผมแนะนำคือให้ทีมมองงานนี้เป็น **Reusable RAG Retrieval Engine** ไม่ใช่แค่โปรเจกต์ทดลอง RAG และให้ MCP/LCEL เป็น adapter ที่อยู่ด้านบน

#### ภาพรวมที่ต้องการ

เป้าหมายคือสร้าง **Two-Stage Hybrid RAG Engine** ที่มี 4 ชั้นหลัก:

```text
                    ┌──────────────────────────────┐
                    │        Consumers             │
                    │                              │
                    │ Agent / App / Agent Platform │
                    └──────────────┬───────────────┘
                                   │
                         ┌─────────┴─────────┐
                         │     Adapters      │
                         │                   │
                         │ Direct LCEL       │
                         │ FastMCP            │
                         └─────────┬─────────┘
                                   │
                    ┌──────────────▼──────────────┐
                    │       RAG Service           │
                    │ search_company_knowledge()  │
                    └──────────────┬──────────────┘
                                   │
                    ┌──────────────▼──────────────┐
                    │    Two-Stage Retrieval      │
                    │                              │
                    │ Stage 1                     │
                    │ Dense + FTS + JSONB + RRF    │
                    │                              │
                    │ Stage 2                     │
                    │ FlashRank Cross Encoder      │
                    └──────────────┬──────────────┘
                                   │
                    ┌──────────────▼──────────────┐
                    │ PostgreSQL + pgvector        │
                    └──────────────────────────────┘
```

##### หลักคิดสำคัญ

**Core ต้องไม่รู้จัก MCP**

MCP เป็นเพียงช่องทางหนึ่งในการ expose capability

ดังนั้นแกนกลางควรเป็น:

```text
HybridRetriever
       ↓
RAGService
       ↓
Direct Adapter / MCP Adapter / future REST Adapter
```

จะทำให้ภายหลัง Agent Platform เรียกใช้ได้หลายวิธีโดยไม่ต้องแก้ retrieval engine

---

#### 1. Retrieval Architecture

Stage 1:

```text
Query
 │
 ├── Dense HNSW
 │      └── metadata @> filter
 │
 └── Sparse FTS
        └── metadata @> filter
              │
              ▼
             RRF
              │
              ▼
        candidate_k
```

Stage 2:

```text
candidate documents
        │
        ▼
FlashRank
        │
        ▼
final top_k
```

ต้องรักษา **metadata filter ตั้งแต่ SQL layer** ห้าม retrieve แล้วค่อย filter ใน Python

นี่เป็นทั้งเรื่อง correctness และ security

---

#### 2. Database Design

ใช้:

```text
PostgreSQL
   +
pgvector
```

ตารางหลัก:

```text
langchain_hybrid_docs
```

Indexes:

```text
HNSW       → vector search
GIN        → tsvector
GIN        → JSONB metadata
```

ควรใช้ `gen_random_uuid()` + `pgcrypto` แทน `uuid_generate_v4()` เพื่อให้ schema เรียบง่ายกว่า

สำหรับ HNSW:

```text
m = 16
ef_construction = 64
ef_search = 40
```

และที่สำคัญ:

> `SET LOCAL hnsw.ef_search = 40` ต้องเกิดใน transaction/connection เดียวกับ query

เพื่อให้ทำงานถูกต้องกับ connection pool

---

#### 3. RRF ต้องกำหนดเป็น Contract

กำหนดชัดเจน:

```text
RRF(k=60)

score =
    1 / (60 + dense_rank)
  + 1 / (60 + sparse_rank)
```

โดย rank เริ่มจาก 1

และกำหนด:

```text
dense_k
sparse_k
candidate_k
final_k
```

ให้เป็น configuration ไม่ hard-code กระจายทั่วระบบ

ตัวอย่าง:

```text
dense_k     = 10
sparse_k    = 10
candidate_k = 10
final_k     = 3
rrf_k       = 60
```

---

### 4. แยก Component ภายใน

แม้จะยังใช้ `rag_engine.py` ตาม deliverable ก็ควรออกแบบภายในประมาณนี้:

```text
HybridRetriever
├── DenseRetriever
├── SparseRetriever
├── RRFFuser
└── CrossEncoderReranker

RAGService
└── search_company_knowledge()

DirectRunner
└── LCEL + ChatOpenAI

MCPServer
└── FastMCP Adapter

Evaluation
├── GroundTruth
├── Metrics
└── Benchmark
```

ถ้าทีมเห็นว่า code เริ่มใหญ่ ให้แยก package ภายหลังได้ เช่น:

```text
rag_engine/
├── storage.py
├── retrieval.py
├── reranker.py
├── service.py
├── direct.py
├── mcp.py
└── evaluation.py
```

แต่ **v1 สามารถเริ่มด้วย 3–4 files ตาม deliverable ได้**

---

### 5. Test Harness ต้องเป็น First-Class Component

อย่าทำ test harness เป็น script ที่แค่เช็กว่า "เรียกได้"

ต้องใช้เป็น **RAG Evaluation Framework รุ่นแรก**

มี Ground Truth:

```text
Query
Expected Document IDs
Metadata Scope
```

Metrics:

```text
Hit@K
Recall@K
MRR
Metadata Leakage
Latency
```

โดยแยก:

```text
Stage 1 metrics
Stage 2 metrics
```

เพื่อให้ตอบได้ว่า:

> FlashRank ช่วย retrieval quality จริงแค่ไหน?

---

### 6. Benchmark Matrix

ทุก query ต้องวิ่งผ่าน 3 strategy:

```text
A. Dense only

B. Dense + FTS + RRF

C. Dense + FTS + RRF + FlashRank
```

แล้วเปรียบเทียบ:

```text
                Hit@K    Recall@K    MRR
Dense
Hybrid
Hybrid+Rerank
```

และ latency:

```text
                p50       p95
Dense           xx ms     xx ms
Hybrid          xx ms     xx ms
Hybrid+Rerank   xx ms     xx ms
```

---

### 7. แยก Retrieval Latency กับ Generation Latency

อันนี้ขอให้ทีมทำตั้งแต่แรก

อย่างน้อย:

```text
dense_ms
sparse_ms
rrf_ms
rerank_ms
retrieval_total_ms
generation_ms
e2e_ms
```

เพราะถ้า ChatOpenAI ช้า จะได้ไม่สรุปผิดว่า RAG ช้า

---

### 8. เพิ่ม Offline Benchmark

แนะนำให้มี 2 modes:

```text
integration
benchmark
```

##### Integration

ใช้ของจริง:

```text
PostgreSQL
OpenAI Embedding
FlashRank
MCP
```

##### Benchmark

ใช้ fixture/precomputed embeddings และ deterministic dataset

ข้อดี:

- ไม่เสีย API cost
- ทำ regression test ได้
- CI ทำได้
- เปรียบเทียบ commit ต่อ commit ได้
- reproducible

---

### 9. MCP Contract

FastMCP expose เพียง capability:

```text
search_company_knowledge(
    query,
    department?,
    document_type?,
    final_k=2
)
```

MCP test ต้องตรวจ:

```text
start server
    ↓
initialize
    ↓
list tools
    ↓
assert search_company_knowledge
    ↓
call tool
    ↓
validate response
    ↓
validate metadata filtering
    ↓
validate stdio integrity
    ↓
shutdown
```

โดยเฉพาะ `stdio`:

```text
stdout = MCP JSON-RPC only
stderr = logs
```

ห้ามมี debug/log หลุด stdout

---

### 10. Definition of Done

ทีมไม่ควรปิดงานเพียงเพราะ "code รันได้"

ต้องผ่านทั้งหมด:

```text
[ ] schema.sql รันได้จาก clean PostgreSQL
[ ] pgvector indexes ถูกสร้าง
[ ] ingestion ทำงาน
[ ] Dense retrieval ทำงาน
[ ] FTS retrieval ทำงาน
[ ] JSONB pre-filter ทำงาน
[ ] RRF ทำงาน
[ ] FlashRank ทำงาน
[ ] final top_k ถูกต้อง
[ ] Direct LCEL mode ทำงาน
[ ] FastMCP mode ทำงาน
[ ] stdio ไม่มี stdout contamination
[ ] MCP client integration test ผ่าน
[ ] Ground-truth evaluation ผ่าน
[ ] Hit@K / Recall@K / MRR คำนวณได้
[ ] metadata leakage test = 0
[ ] p50/p95 latency แสดงผล
[ ] Dense vs Hybrid vs Rerank benchmark แสดงผล
[ ] offline benchmark ทำงาน
[ ] integration benchmark ทำงาน
```

---

### 11. Deliverable ที่ทีมควรส่งกลับ

ผมแนะนำให้ขยายจาก 4 files เดิมเป็น:

```text
schema.sql
requirements.txt
rag_engine.py
test_harness.py
README.md
.env.example
docker-compose.yml
```

โดยเฉพาะ `docker-compose.yml` จะเหมาะกับ workflow ของทีมมาก เพราะสามารถทำ:

```bash
docker compose up -d
python test_harness.py
```

แล้วเห็น benchmark ได้ทันที

---

### 12. สิ่งที่ไม่ควรทำ

ฝากทีมหลีกเลี่ยง 5 อย่างนี้:

```text
❌ MCP logic ฝังอยู่ใน retrieval core
❌ filter หลังจาก retrieval
❌ ใช้ OpenAI generation latency เป็น retrieval latency
❌ benchmark ที่ไม่มี ground truth
❌ test ที่ต้องเสีย OpenAI API ทุกครั้ง
```

และอย่า optimize prematurely เช่น tuning HNSW หลายสิบ parameter ก่อนมี benchmark baseline

**ต้องสร้าง baseline → วัด → ปรับ → วัดใหม่**

---

### 13. Positioning ใน Agent Platform

ตัวนี้ผมแนะนำให้ทีมวางตำแหน่งเป็น:

```text
Agent Platform
      │
      ├── Model / Coding Agents
      │
      ├── Harness
      │
      ├── Tool / MCP Layer
      │
      └── Knowledge / RAG
              │
              ▼
       Hybrid RAG Engine
```

ดังนั้น RAG Engine **ไม่ใช่ Agent**

และไม่ควรพยายามใส่ agent loop, planning, memory, orchestration เข้าไปใน repo นี้

มันควรทำหน้าที่เดียวให้ดีมาก:

> **Retrieve the right enterprise knowledge, with measurable quality, latency, and strict metadata isolation.**

จากนั้น MCP ทำให้ Agent Platform สามารถ consume capability นี้ได้ทันที

---

#### ลำดับการทำงานที่แนะนำให้ทีม

```text
Phase 1
Database + ingestion
        ↓
Phase 2
Dense + FTS + RRF
        ↓
Phase 3
FlashRank
        ↓
Phase 4
RAGService abstraction
        ↓
Phase 5
Direct LCEL
        ↓
Phase 6
FastMCP
        ↓
Phase 7
Ground-truth evaluation
        ↓
Phase 8
Benchmark + latency
        ↓
Phase 9
Offline regression suite
        ↓
Phase 10
Docker + CI + documentation
```

**หัวใจของงานนี้คืออย่าเริ่มจาก MCP หรือ LangChain แต่ให้เริ่มจาก Retrieval Core + Evaluation ก่อน** แล้วค่อยเอา LCEL/MCP มาครอบด้านบน แบบนี้จะได้ component ที่สามารถนำไปต่อกับ Agent Platform, Enterprise RAG และ agent ต่าง ๆ ได้ในอนาคตครับ

---

## 👤 ผู้ใช้ — ข้อความที่ 5

ทีมฝากถาม มีส่วนเกี่ยวข้องกับ https://github.com/monthop-gmail/agent-platform เราด้วยใหม

---

> 🔧 *tool call — The output of this plugin was redacted.*

> 🔧 *tool call — The output of this plugin was redacted.*

> 🔧 *tool call — The output of this plugin was redacted.*

> 🔧 *tool call — The output of this plugin was redacted.*

> 🔧 *tool call — The output of this plugin was redacted.*

> 🔧 *tool call — The output of this plugin was redacted.*

## 🤖 ChatGPT — ข้อความที่ 6

มีครับ — และจากที่ตรวจ `agent-platform` ตอนนี้ **เกี่ยวข้องโดยตรง แต่ไม่ควรเอา RAG Engine ไปใส่ใน `agent-platform`** ครับ

ใน `agent-platform` ระบุชัดว่า repo นี้เป็น **core platform ที่ถือ architecture / contracts / ADR / plane boundaries** ส่วน implementation จริงอยู่ใน consumer/product repo 

ที่สำคัญคือ `knowledge` plane ของ platform กำหนดหน้าที่ไว้ตรงกับงานที่เรากำลังทำเกือบพอดี:

```text
Ingest
 → Parse
 → Classify
 → Chunk
 → Embed
 → Index
 → Retrieve
 → Feedback
 → Re-index
```

และระบุ **hybrid retrieval + reranking** รวมถึง ACL / tenant boundary ด้วย 

#### ดังนั้นผมแนะนำความสัมพันธ์แบบนี้

```text
                    agent-platform
                  ┌─────────────────┐
                  │ CORE / CONTRACT │
                  │                 │
                  │ knowledge plane │
                  │ tool/v1         │
                  │ identity/v1     │
                  │ policy/v1       │
                  └────────┬────────┘
                           │ contract
                           ▼
              ┌─────────────────────────┐
              │   enterprise-knowledge │
              │   IMPLEMENTATION        │
              │                         │
              │ ingestion               │
              │ PostgreSQL/pgvector     │
              │ hybrid retrieval       │
              │ RRF                     │
              │ reranker                │
              │ provenance              │
              │ ACL enforcement         │
              │ MCP/tool adapter        │
              │ evaluation              │
              └─────────────────────────┘
                           │
                           ▼
                    Agent Platform
                    Tool / MCP
                           │
                           ▼
                     Agents / Apps
```

##### สรุปง่าย ๆ

**`agent-platform` = กำหนดว่า Knowledge capability ต้องมีหน้าตาอย่างไร**

**`enterprise-knowledge` = ลงมือสร้าง Knowledge capability นั้น**

ดังนั้น RAG Engine ที่เราคุยกัน **ควรเป็น implementation ของ `enterprise-knowledge`** มากกว่าเป็น implementation ใน `agent-platform`

---

#### แต่ prompt ปัจจุบันยังขาดเรื่อง Platform Contract

นี่คือสิ่งที่ผมแนะนำให้ทีมเพิ่มเข้าไป

จากเดิม:

```text
search_company_knowledge(...)
```

อย่าให้เป็น contract เฉพาะของ RAG Engine อย่างเดียว

ควรมี canonical capability:

```text
knowledge.search
```

แล้ว implementation ภายในค่อยใช้:

```text
Dense
+
FTS
+
RRF
+
FlashRank
```

เช่น conceptually:

```text
knowledge.search
{
  query,
  scope,
  filters,
  top_k
}
        ↓
Enterprise Knowledge
        ↓
Hybrid RAG Engine
```

แบบนี้ภายหลังจะเปลี่ยนจาก PostgreSQL → Elasticsearch → graph → hybrid vector DB ก็ไม่กระทบ Agent Platform contract

---

### จุดสำคัญที่สุด: ACL

ตรงนี้ผมอยาก **ยกระดับจาก prompt เดิม**

ใน `agent-platform` ระบุชัดว่า Knowledge plane ห้ามมี retrieval ที่ไม่ enforce ACL และห้ามข้าม tenant boundary 

ดังนั้น RAG Engine รุ่นนี้ไม่ควรมีเพียง:

```text
department
document_type
```

แต่ควรเตรียม abstraction สำหรับ:

```text
tenant_id
principal_id
roles
groups
department
document_type
classification
```

แล้ว retrieval ต้องเป็น:

```text
Query
  ↓
Identity Context
  ↓
Policy / ACL Scope
  ↓
SQL pre-filter
  ↓
Dense + FTS
  ↓
RRF
  ↓
Rerank
  ↓
Results
```

**ไม่ใช่**

```text
Query
 ↓
Retrieve everything
 ↓
filter ACL
```

เพราะแบบหลังมีความเสี่ยงสูงมาก

---

### ผมจะแนะนำทีมแบ่งงานแบบนี้

##### ทีม `agent-platform`

ไม่ต้องเขียน RAG code

ให้ทำ:

- `knowledge.search` contract
- request/response schema
- identity/policy integration contract
- ACL semantics
- provenance/citation contract
- capability definition
- conformance requirements

##### ทีม `enterprise-knowledge`

เอา prompt ที่เราปรับเมื่อกี้ไปสร้าง:

- PostgreSQL + pgvector
- ingestion
- hybrid retrieval
- RRF
- FlashRank
- evaluation
- benchmark
- MCP adapter
- Docker Compose
- implementation ของ `knowledge.search`

---

#### และมีอีกเรื่องที่สำคัญ

ใน `agent-platform` ตอนนี้ระบุว่า:

> `enterprise-knowledge` — **ยังไม่มี repo**

ดังนั้นงาน RAG นี้เป็นจังหวะที่เหมาะมากที่จะ **เริ่ม repo `monthop-gmail/enterprise-knowledge`** ให้ตรงกับ architecture ที่ platform กำหนดไว้เลย 

ผมจึง **ไม่แนะนำสร้าง repo ชื่อ `hybrid-rag-engine` เป็น product หลัก**

แต่ให้:

```text
monthop-gmail/agent-platform
        │
        │ contract
        ▼
monthop-gmail/enterprise-knowledge
        │
        ├── enterprise RAG
        ├── Hybrid Retrieval
        ├── pgvector
        ├── Reranker
        ├── ACL
        ├── Provenance
        ├── Evaluation
        └── MCP / knowledge.search
```

แล้ว **Two-Stage Hybrid RAG Engine เป็น module ภายใน `enterprise-knowledge`**

นี่จะ align กับ architecture ที่ทีมวางไว้แล้วมากที่สุดครับ

**ดังนั้นคำตอบสำหรับทีมคือ: "เกี่ยวข้องโดยตรงกับ agent-platform ในระดับ contract/plane แต่ implementation ให้ไปอยู่ `enterprise-knowledge` ไม่ใช่ `agent-platform`"**

---

## 👤 ผู้ใช้ — ข้อความที่ 7

ขอ ภาพรวมและแนวทาง ฉบับสมบูรณ์ส่งทีมจร้า

---

## 🤖 ChatGPT — ข้อความที่ 8

ได้เลยครับ ฉบับนี้ผมแนะนำให้ส่งทีมเป็น **master direction ของ `enterprise-knowledge`** เลย เพราะมันเชื่อม `agent-platform` กับ Two-Stage Hybrid RAG ที่คุยกันได้ครบ และไม่ทำให้ responsibility ของแต่ละ repo ปนกัน

:::writing{variant="document" id="58321" title="Enterprise Knowledge — ภาพรวมและแนวทางการพัฒนา"}

### Enterprise Knowledge — ภาพรวมและแนวทางการพัฒนา

#### 1. เป้าหมาย

สร้าง `enterprise-knowledge` เป็น **Knowledge Plane Implementation** ของ `agent-platform`

หน้าที่หลักคือทำให้ Agent และ Application สามารถค้นหาและใช้งานความรู้ขององค์กรได้อย่าง:

- ถูกต้อง
- เร็ว
- ตรวจสอบย้อนกลับได้
- มี provenance
- enforce ACL
- enforce tenant isolation
- รองรับ hybrid retrieval
- มี evaluation และ regression benchmark
- expose ผ่าน canonical `knowledge.search`
- รองรับ MCP เป็นหนึ่งใน transport/adapters

`agent-platform` เป็นเจ้าของ **contract / architecture / policy semantics**

`enterprise-knowledge` เป็นเจ้าของ **implementation**

---

### 2. ความสัมพันธ์กับ Agent Platform

```text
                         agent-platform
                    ┌──────────────────────┐
                    │ CORE / GOVERNANCE    │
                    │                      │
                    │ contracts            │
                    │ profiles             │
                    │ ADR                  │
                    │ knowledge plane      │
                    │ identity / policy    │
                    └──────────┬───────────┘
                               │
                         canonical contract
                               │
                               ▼
                 ┌───────────────────────────┐
                 │    enterprise-knowledge   │
                 │                           │
                 │ Knowledge Implementation   │
                 │                           │
                 │ Ingestion                 │
                 │ Parsing / Chunking        │
                 │ Embedding                 │
                 │ Indexing                  │
                 │ Hybrid Retrieval          │
                 │ Reranking                 │
                 │ ACL / Tenant Filtering    │
                 │ Provenance / Citation     │
                 │ Evaluation                │
                 └─────────────┬─────────────┘
                               │
                         knowledge.search
                               │
                 ┌─────────────┴─────────────┐
                 │                           │
              MCP Adapter               Direct Adapter
                 │                           │
                 ▼                           ▼
              Agents                    Applications
```

**ห้ามนำ implementation ของ RAG Engine ไปไว้ใน `agent-platform`**

`agent-platform` ควรเป็น core ที่ถือ contract และ boundary เท่านั้น

---

### 3. Knowledge Plane Boundary

Knowledge Plane มี lifecycle หลัก:

```text
Ingest
  ↓
Parse
  ↓
Classify
  ↓
Chunk
  ↓
Embed
  ↓
Index
  ↓
Retrieve
  ↓
Rerank
  ↓
Cite / Provenance
  ↓
Feedback
  ↓
Re-index
```

แหล่งข้อมูลในอนาคตสามารถมาจาก:

- GitHub
- Odoo
- Database
- Files
- Web
- Email
- IoT
- Enterprise applications

แต่ retrieval ต้องผ่าน policy/identity boundary ของ platform

---

### 4. หลักการสำคัญ

#### 4.1 Retrieval Core ต้องไม่ผูกกับ MCP

MCP เป็น adapter

ไม่ใช่ core architecture

```text
HybridRetriever
      ↓
KnowledgeService
      ↓
 ┌────┴─────┐
 ▼          ▼
MCP       Direct
```

ในอนาคตสามารถเพิ่ม REST, SDK หรือ internal service adapter ได้โดยไม่ต้องแก้ retrieval engine

---

#### 4.2 Retrieval ต้อง enforce ACL ก่อน retrieval

ห้าม:

```text
Retrieve all
   ↓
Filter ACL
```

ต้องเป็น:

```text
Identity
   ↓
Policy / ACL Scope
   ↓
SQL Pre-filter
   ↓
Dense + Sparse Retrieval
   ↓
RRF
   ↓
Reranking
```

เพราะการเห็น document ที่ไม่มีสิทธิ์แม้เพียงชั่วคราวถือเป็น security violation

---

#### 4.3 Tenant Isolation ต้องเป็น hard boundary

ทุก query ที่อยู่ใน multi-tenant environment ต้องมี tenant scope

เช่น:

```text
tenant_id
principal_id
roles
groups
department
document_type
classification
```

Tenant boundary ห้ามถูก bypass โดย application หรือ agent

---

### 5. Two-Stage Hybrid RAG

#### Stage 1 — Candidate Retrieval

ใช้:

```text
Dense Vector Search
        +
Sparse Full-Text Search
        +
JSONB Pre-filter
        ↓
       RRF
        ↓
 candidate_k
```

Database:

```text
PostgreSQL
+
pgvector
```

Dense:

```text
HNSW
Cosine Distance
text-embedding-3-small
```

Sparse:

```text
PostgreSQL tsvector
+
ts_rank_cd
```

Metadata:

```text
JSONB
+
GIN index
```

---

### 6. RRF Specification

ต้องกำหนดเป็น canonical behavior:

```text
RRF(k=60)

score =
    1 / (60 + dense_rank)
  + 1 / (60 + sparse_rank)
```

rank เริ่มจาก `1`

configuration อย่างน้อย:

```text
dense_k
sparse_k
candidate_k
final_k
rrf_k
```

ตัวอย่าง default:

```text
dense_k     = 10
sparse_k    = 10
candidate_k = 10
final_k     = 3
rrf_k       = 60
```

ค่าทั้งหมดควร configurable

---

### 7. Stage 2 — Cross Encoder

ใช้:

```text
FlashRank
ms-marco-TinyBERT-L-2-v2
ONNX Runtime
CPU
```

Flow:

```text
RRF candidates
      ↓
Cross Encoder
      ↓
Re-sort
      ↓
final_k
```

ต้องวัด latency แยกจาก database retrieval

---

### 8. PostgreSQL Design

Table หลัก:

```text
langchain_hybrid_docs
```

fields:

```text
id
content
metadata
embedding
tsv_content
```

แนะนำใช้:

```text
gen_random_uuid()
```

ผ่าน `pgcrypto`

แทนการผูกกับ `uuid-ossp`

Indexes:

```text
HNSW
embedding vector_cosine_ops

GIN
tsv_content

GIN
metadata jsonb_path_ops
```

---

### 9. HNSW Connection Safety

เนื่องจากใช้ `psycopg ConnectionPool`

ต้องทำ:

```text
BEGIN
  SET LOCAL hnsw.ef_search = 40
  execute vector query
COMMIT
```

หรือ equivalent ที่ guarantee ว่า `ef_search` และ vector query อยู่ connection/transaction เดียวกัน

ห้ามตั้ง session parameter แบบไม่ deterministic แล้วคืน connection เข้า pool

---

### 10. Canonical Service

Core API ของ implementation ควรมี concept:

```python
knowledge.search(...)
```

เช่น:

```text
query
tenant_id
principal
filters
top_k
```

โดย response ควรเตรียมรองรับ:

```text
documents
score
source
document_id
chunk_id
metadata
provenance
citation
```

ชื่อภายในสามารถแตกต่างได้ แต่ semantics ต้อง align กับ contract ของ `agent-platform`

---

### 11. MCP Adapter

MCP สามารถ expose:

```text
search_company_knowledge(...)
```

แต่ต้องถือว่าเป็น adapter ของ:

```text
knowledge.search
```

ไม่ใช่ contract ใหม่ที่แยกออกจาก platform

ตัวอย่าง:

```text
MCP Tool
    ↓
KnowledgeService.search()
    ↓
ACL Scope
    ↓
Hybrid Retrieval
    ↓
Reranker
    ↓
Response
```

---

### 12. MCP stdio Integrity

ใน stdio:

```text
stdout = MCP JSON-RPC only
stderr = logs
```

ห้าม:

```python
print("debug")
```

ลง stdout

MCP integration test ต้องตรวจ stdout contamination ด้วย

---

### 13. Direct Execution

รองรับ Direct mode สำหรับ development / testing:

```text
Direct
  ↓
KnowledgeService
  ↓
Context
  ↓
LCEL
  ↓
ChatOpenAI
```

แต่ Generation ต้องแยกจาก Retrieval

เพื่อให้สามารถ benchmark retrieval โดยไม่ต้องเรียก LLM ได้

---

### 14. Component Architecture

ภายใน implementation ควรแยก responsibility:

```text
enterprise-knowledge
│
├── Storage
│   └── PostgreSQL / pgvector
│
├── Ingestion
│   ├── Parser
│   ├── Chunker
│   └── Embedder
│
├── Retrieval
│   ├── DenseRetriever
│   ├── SparseRetriever
│   ├── RRFFuser
│   └── HybridRetriever
│
├── Reranking
│   └── FlashRank
│
├── Security
│   ├── TenantScope
│   ├── ACL
│   └── PolicyContext
│
├── KnowledgeService
│
├── Adapters
│   ├── MCP
│   └── Direct / LCEL
│
├── Provenance
│
└── Evaluation
    ├── GroundTruth
    ├── Metrics
    └── Benchmark
```

ถ้า implementation โต สามารถแยกเป็น package ตาม structure นี้ได้

---

### 15. Evaluation Framework

Evaluation เป็น first-class capability

ไม่ใช่ script ที่เขียนเพื่อ demo เท่านั้น

Ground truth:

```text
Query
Expected Document IDs
Metadata Scope
```

Metrics:

```text
Hit@K
Recall@K
MRR
Metadata Leakage
Latency
```

ต้องวัดทั้ง:

```text
Stage 1
Stage 2
```

เพื่อดูว่า reranker เพิ่มคุณภาพจริงหรือไม่

---

### 16. Benchmark Matrix

ทุก query ต้องถูกประเมินอย่างน้อย 3 strategy:

```text
A. Dense only

B. Dense + FTS + RRF

C. Dense + FTS + RRF + FlashRank
```

เปรียบเทียบ:

```text
Hit@K
Recall@K
MRR
p50
p95
```

ตัวอย่าง:

```text
Strategy              Hit@K   Recall@K   MRR     p50    p95
----------------------------------------------------------------
Dense                   ...
Hybrid                  ...
Hybrid + Rerank         ...
```

---

### 17. Latency Breakdown

ต้องแยก:

```text
dense_ms
sparse_ms
rrf_ms
rerank_ms
retrieval_total_ms
generation_ms
e2e_ms
```

เพื่อให้รู้ว่า bottleneck อยู่ตรงไหน

ห้ามใช้ E2E latency อย่างเดียวแล้วสรุปว่า retrieval engine เร็ว/ช้า

---

### 18. Offline vs Integration Benchmark

ต้องมีอย่างน้อย 2 modes

#### Offline

ใช้:

- fixture dataset
- precomputed embeddings
- deterministic ground truth
- local reranker

เป้าหมาย:

- CI
- regression
- algorithm comparison
- ไม่เสีย API cost

#### Integration

ใช้:

- PostgreSQL จริง
- pgvector จริง
- embedding service จริง
- FlashRank จริง
- MCP จริง

เป้าหมาย:

- end-to-end validation
- production-like benchmark

---

### 19. MCP Functional Test

Test flow:

```text
Start server
    ↓
Initialize MCP session
    ↓
List tools
    ↓
Verify knowledge search tool
    ↓
Call tool
    ↓
Validate response
    ↓
Validate metadata / ACL scope
    ↓
Validate stdout integrity
    ↓
Shutdown
```

ต้องทดสอบผ่าน MCP protocol จริง ไม่ใช่เรียก Python function ตรง ๆ แล้วเรียกว่า MCP test

---

### 20. Suggested Repository

ควรสร้าง:

```text
monthop-gmail/enterprise-knowledge
```

ไม่แนะนำตั้ง repo หลักเป็น:

```text
hybrid-rag-engine
rag-engine
mcp-rag
```

เพราะสิ่งที่กำลังสร้างใหญ่กว่า RAG engine

RAG เป็น implementation ภายใน Knowledge Plane

---

### 21. Suggested Repository Structure

```text
enterprise-knowledge/
│
├── README.md
├── requirements.txt
├── pyproject.toml
├── .env.example
├── docker-compose.yml
│
├── schema.sql
│
├── src/
│   └── enterprise_knowledge/
│       ├── storage.py
│       ├── ingestion.py
│       ├── embeddings.py
│       ├── retrieval.py
│       ├── reranker.py
│       ├── security.py
│       ├── provenance.py
│       ├── service.py
│       ├── direct.py
│       └── mcp.py
│
├── tests/
│   ├── unit/
│   ├── integration/
│   └── mcp/
│
├── evaluation/
│   ├── ground_truth.py
│   ├── metrics.py
│   └── benchmark.py
│
└── docs/
    ├── architecture.md
    ├── retrieval.md
    ├── security.md
    └── evaluation.md
```

สามารถเริ่มเล็กกว่านี้ได้ แต่ควรรักษา boundary นี้ไว้

---

### 22. Docker Compose

ต้องสามารถ bootstrap local environment ได้ง่าย:

```text
docker compose up -d
```

อย่างน้อย:

```text
PostgreSQL + pgvector
```

และ optionally:

```text
MCP / RAG service
```

เป้าหมายคือ developer ใหม่สามารถ clone → compose → test ได้เร็ว

---

### 23. Definition of Done

#### Core

- [ ] PostgreSQL schema ทำงานจาก clean database
- [ ] pgvector extension
- [ ] HNSW index
- [ ] FTS GIN index
- [ ] JSONB GIN index
- [ ] ingestion
- [ ] embedding
- [ ] Dense retrieval
- [ ] Sparse retrieval
- [ ] RRF
- [ ] FlashRank reranking

#### Security

- [ ] tenant isolation
- [ ] metadata scope
- [ ] ACL pre-filter
- [ ] ไม่มี unauthorized result leakage
- [ ] policy context ไม่ถูก bypass

#### Interfaces

- [ ] canonical `knowledge.search`
- [ ] Direct mode
- [ ] MCP adapter
- [ ] MCP stdio integrity
- [ ] structured response

#### Evaluation

- [ ] Ground truth
- [ ] Hit@K
- [ ] Recall@K
- [ ] MRR
- [ ] metadata leakage
- [ ] p50
- [ ] p95
- [ ] Dense vs Hybrid vs Reranker
- [ ] offline benchmark
- [ ] integration benchmark

#### Operations

- [ ] Docker Compose
- [ ] `.env.example`
- [ ] tests
- [ ] README
- [ ] CI-ready
- [ ] reproducible benchmark

---

### 24. Implementation Phases

#### Phase 1 — Foundation

สร้าง:

```text
PostgreSQL
pgvector
schema
connection pool
ingestion
embedding
```

#### Phase 2 — Retrieval

สร้าง:

```text
Dense
FTS
JSONB filtering
RRF
```

#### Phase 3 — Reranking

เพิ่ม:

```text
FlashRank
```

พร้อม latency instrumentation

#### Phase 4 — Service Boundary

สร้าง:

```text
KnowledgeService
knowledge.search
```

และแยก retrieval จาก generation

#### Phase 5 — Adapters

เพิ่ม:

```text
Direct LCEL
FastMCP
```

#### Phase 6 — Evaluation

เพิ่ม:

```text
Ground Truth
Hit@K
Recall@K
MRR
Leakage
```

#### Phase 7 — Benchmark

เพิ่ม:

```text
Dense
Hybrid
Hybrid + Reranker
```

พร้อม p50/p95

#### Phase 8 — Security

เพิ่ม:

```text
tenant
principal
roles
ACL
policy integration
```

#### Phase 9 — Integration

เชื่อม:

```text
agent-platform contracts
knowledge.search
identity
policy
tool/MCP
```

#### Phase 10 — Production Hardening

ทำ:

```text
Docker
CI
Regression
Observability
Documentation
Performance tuning
```

---

### 25. สิ่งที่ไม่ควรทำ

ห้าม:

```text
❌ ใส่ implementation ลง agent-platform
❌ ทำ MCP เป็น core
❌ ทำ retrieval แล้วค่อย filter ACL
❌ ให้ tenant filter เป็น optional ใน production path
❌ ผูก Knowledge Plane กับ vendor รายเดียว
❌ benchmark โดยไม่มี ground truth
❌ benchmark ที่ต้องยิง LLM ทุกครั้ง
❌ รวม generation latency กับ retrieval latency
❌ optimize HNSW ก่อนมี baseline
❌ สร้าง agent loop ใน enterprise-knowledge
```

---

### 26. หลักการพัฒนา

ลำดับการ optimize:

```text
Correctness
    ↓
Security
    ↓
Evaluation
    ↓
Baseline
    ↓
Performance
    ↓
Scale
```

ไม่ใช่:

```text
Performance
    ↓
แล้วค่อยถามว่าผลลัพธ์ถูกหรือไม่
```

โดยเฉพาะ Enterprise Knowledge ต้องถือว่า:

> **Unauthorized retrieval = failure แม้ answer จะถูกต้อง**

---

### 27. ผลลัพธ์สุดท้ายที่ต้องการ

เมื่อเสร็จแล้ว ecosystem ควรมีรูปแบบ:

```text
                         agent-platform
                              │
                    contracts / policy
                              │
                              ▼
                   enterprise-knowledge
                              │
                    ┌─────────┴─────────┐
                    │                   │
              knowledge.search       MCP
                    │                   │
                    └─────────┬─────────┘
                              ▼
                     Hybrid RAG Engine
                              │
                ┌─────────────┼─────────────┐
                ▼             ▼             ▼
             Dense           FTS          RRF
                └─────────────┼─────────────┘
                              ▼
                         FlashRank
                              │
                              ▼
                     Provenance/Citation
                              │
                              ▼
                         Agent / App
```

จุดสำคัญคือ **Agent ไม่จำเป็นต้องรู้ว่า Knowledge backend ใช้ PostgreSQL, pgvector, FTS, RRF หรือ FlashRank**

Agent รู้เพียง:

```text
knowledge.search
```

ส่วน `enterprise-knowledge` เป็นผู้รับผิดชอบทำให้ capability นั้นมีคุณภาพและปลอดภัย

---

### 28. Final Direction

ให้ถือ architecture นี้เป็นหลัก:

```text
agent-platform
    = Contract + Governance + Plane Boundary

enterprise-knowledge
    = Knowledge Plane Implementation

Hybrid RAG
    = Retrieval Engine ภายใน enterprise-knowledge

MCP
    = Adapter / Tool Interface

Evaluation
    = Quality Gate

ACL / Tenant Isolation
    = Security Boundary

PostgreSQL + pgvector
    = Initial Storage / Retrieval Backend
```

เป้าหมายไม่ใช่แค่สร้าง "RAG ที่ค้นหาได้"

แต่คือสร้าง **Enterprise Knowledge Capability ที่ Agent Platform สามารถนำไปใช้ซ้ำกับหลาย product, หลาย agent และหลายองค์กรได้ โดยมี contract, security, provenance, evaluation และ performance เป็นส่วนหนึ่งของระบบตั้งแต่ต้น**

:::

**หมายเหตุสำหรับทีม:** จาก `agent-platform` ปัจจุบัน `knowledge` plane ถูกกำหนดไว้แล้วว่าเป็นพื้นที่สำหรับ ingest/retrieve/provenance/citation และต้อง enforce ACL/tenant boundary ขณะที่ implementation ถูกระบุไว้เป็น `enterprise-knowledge` ซึ่งยังไม่มี repo ดังนั้นงานนี้ถือเป็น implementation ที่ตรงกับช่องว่างนั้นโดยตรง

---
