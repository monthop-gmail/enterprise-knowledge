# Architecture

อ้างอิง: [`ref/hybrid-rag-prompt-review.md`](../ref/hybrid-rag-prompt-review.md) §2, §4, §14, §28

## Boundary

```
agent-platform          = contract + governance + plane boundary
enterprise-knowledge    = knowledge plane implementation   <-- repo นี้
hybrid RAG              = retrieval engine ภายใน repo นี้
MCP                     = adapter / tool interface
evaluation              = quality gate
ACL / tenant isolation  = security boundary
PostgreSQL + pgvector   = initial storage backend
```

กฎข้อเดียวที่ห้ามละเมิด: **ห้ามย้าย implementation ของ RAG engine ไปไว้ใน `agent-platform`** (§2)
`agent-platform` ถือ contract กับ policy semantics เท่านั้น

## Layering

```
                      Consumers
          Agent / App / Agent Platform
                          │
                 knowledge.search          <-- สิ่งเดียวที่ consumer รู้จัก (§27)
                          │
        ┌─────────────────┴─────────────────┐
        │           KnowledgeService        │   service.py
        └─────────────────┬─────────────────┘
                          │
     ┌──────────┬─────────┼─────────┬──────────────┐
     ▼          ▼         ▼         ▼              ▼
  security   embeddings  retrieval  reranker   provenance
     │                     │           │
     │                 storage.py      └── FlashRank (stage 2)
     └── ScopePredicate ──┘
                          │
                 PostgreSQL + pgvector

        Adapters (ไม่มี logic ของตัวเอง):  mcp.py   direct.py
```

`RetrievalStrategy` มี 3 ค่า ตรงกับ 3 arm ของ benchmark (§16) — `dense`, `hybrid`, `hybrid_rerank`
adapter ทุกตัวแปลง transport เป็น `SearchRequest` แล้วส่งเข้า service ตัวเดียวกัน ไม่มี pipeline คู่ขนาน

## Module map

| ไฟล์ | ความรับผิดชอบ | สถานะ |
|---|---|---|
| `contracts.py` | canonical types (§10) — stdlib ล้วน ไม่มี dependency | ✅ ครบ |
| `config.py` | `RetrievalConfig` (§6), settings, logging → stderr (§12) | ✅ ครบ |
| `security.py` | `PolicyContext` → `ScopePredicate` (§4.2, §4.3) | ✅ ครบ |
| `retrieval.py` | RRF fusion + stage-1 SQL + bind params (§5, §6) | ✅ RRF/SQL ครบ · execution = Phase 2 |
| `reranker.py` | stage 2 protocol + identity arm (§7) | ✅ contract · FlashRank = Phase 3 |
| `embeddings.py` | `Embedder` protocol + deterministic offline (§25) | ✅ offline ครบ · OpenAI = Phase 1 |
| `provenance.py` | provenance + citation ของทุกผลลัพธ์ (§10) | ✅ ครบ |
| `storage.py` | pool + `SET LOCAL hnsw.ef_search` transaction (§9) | ✅ contract · execution = Phase 1 |
| `ingestion.py` | parse → chunk → embed → upsert (§3) | Phase 1 |
| `service.py` | orchestration + timing breakdown (§13, §17) | ✅ ครบ (รอ retriever) |
| `mcp.py` / `direct.py` | adapters (§11, §13) | Phase 5 |

## ทำไม retrieval ถึงไม่ generate

§13 + §25: ถ้า retrieval เรียก LLM เอง จะ benchmark retrieval แยกไม่ได้ และ latency จะปนกัน
`KnowledgeService.search()` จึงไม่แตะ LLM เลย — `Timings.generation_ms` เป็น `None` เสมอในเส้นทาง retrieval
ใครต้องการคำตอบให้ประกอบ `LcelAnswerer` ทับข้างบน แล้วจับเวลาแยก
