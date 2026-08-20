# enterprise-knowledge

**Knowledge Plane implementation** ของ [`agent-platform`](https://github.com/monthop-gmail/agent-platform)

`agent-platform` เป็นเจ้าของ contract / architecture / policy semantics
repo นี้เป็นเจ้าของ **implementation**: ingestion, hybrid retrieval, reranking, ACL/tenant enforcement,
provenance และ evaluation — expose ออกไปเป็น call เดียวคือ `knowledge.search`

ที่มาของ direction ทั้งหมด: [`ref/hybrid-rag-prompt-review.md`](ref/hybrid-rag-prompt-review.md)
(หมายเลข §N ในโค้ดและ docs อ้างถึงหัวข้อในไฟล์นั้น)

---

## สถานะ: contract skeleton (v0.1.0)

รอบนี้วาง **โครง + contract** ให้ทีมรีวิว boundary ก่อนลง logic จริง

| ส่วน | สถานะ |
|---|---|
| canonical types (`contracts.py`) | ✅ ครบ — stdlib ล้วน ไม่มี dependency |
| ACL / tenant scope predicate | ✅ ครบ + tests |
| RRF fusion (§6) | ✅ ครบ + exact-value tests |
| stage-1 SQL + bind params | ✅ ครบ (ยังไม่ execute) |
| service orchestration + timings | ✅ ครบ |
| provenance / citation | ✅ ครบ |
| offline embedder | ✅ ครบ |
| metrics (Hit@K, Recall@K, MRR, leakage, p50/p95) | ✅ ครบ + tests |
| ground truth fixtures | ✅ ครบ |
| schema.sql + docker-compose | ✅ ครบ — ตรวจแล้วว่ารันจาก clean DB ได้จริง |
| stage-1 SQL ยิงกับ PG16+pgvector จริง | ✅ ตรวจแล้ว — tenant/ACL/filter กันได้จริง |
| SQL execution / ingestion / FlashRank / MCP / LCEL | ⏳ Phase 1–5 |

```
ไม่มี DB : 40 passed ·  6 skipped · 7 xfailed
มี DB    : 46 passed ·              7 xfailed     (ruff clean)
```

ทุกจุดที่ยังไม่ทำ raise `NotImplementedError` พร้อมระบุ phase — ไม่มี stub ที่คืนค่าปลอมเงียบ ๆ

## เริ่มใช้งาน

```bash
cp .env.example .env
make install          # pip install -e '.[dev]'
make test             # unit tests — ไม่ต้องมี DB ไม่ต้องมี API key

make up && make schema   # postgres + pgvector บนพอร์ต 55433
make test-all
```

## Contract

```python
from enterprise_knowledge import KnowledgeService, SearchRequest, resolve_policy, Principal

policy = resolve_policy(
    tenant_id="acme",
    principal=Principal("u-1", roles=frozenset({"staff"})),
    allowed_metadata={"classification": ["public", "internal"]},
)

response = service.search(SearchRequest(query="ลาพักร้อนได้กี่วัน", policy=policy, top_k=3))

for doc in response.documents:
    print(doc.score, doc.citation.label, doc.provenance.document_id)
print(response.timings)   # dense / sparse / rrf / rerank / retrieval_total / e2e
```

consumer รู้จักแค่ `knowledge.search` — ไม่รู้ว่าข้างในเป็น PostgreSQL, pgvector, RRF หรือ FlashRank (§27)

## กฎที่โค้ดบังคับไว้แล้ว

- **ACL ก่อน retrieval** — `ScopePredicate` ถูก splice เข้าไปใน CTE ทั้งสองตัว ไม่ใช่กรองผลลัพธ์ทีหลัง (§4.2)
- **tenant เป็น hard boundary** — `TenantScope("")` โยน error, `filters={"tenant_id": ...}` โยน error (§4.3)
- **MCP เป็น adapter ไม่ใช่ core** — `mcp.py` แปลง payload อย่างเดียว ไม่มี pipeline ของตัวเอง (§4.1, §11)
- **retrieval ไม่ generate** — `KnowledgeService` ไม่แตะ LLM, `generation_ms` แยกเสมอ (§13, §17)
- **leakage เป็น gate ไม่ใช่ score** — `ArmResult.passed` เป็น false ทันทีที่ leak > 0 (§26)
- **ไม่ผูก vendor** — OpenAI / FlashRank / FastMCP / LangChain เป็น optional extras ทั้งหมด (§25)

## โครงสร้าง

```
src/enterprise_knowledge/   contract + engine (ดู docs/architecture.md)
evaluation/                 ground truth · metrics · benchmark matrix
tests/unit/                 ไม่ต้องมี DB — รันใน CI ได้ทุก commit
tests/integration/          ต้องมี PostgreSQL + pgvector จริง
tests/mcp/                  ต้องผ่าน MCP protocol จริง (§19)
docs/                       architecture · retrieval · security · evaluation
ref/                        direction doc ต้นทาง
```

## แผนพัฒนา

📋 **[Roadmap: Phase 1–10](https://github.com/monthop-gmail/enterprise-knowledge/issues/22)** ·
[Milestones](https://github.com/monthop-gmail/enterprise-knowledge/milestones) ·
[Issues](https://github.com/monthop-gmail/enterprise-knowledge/issues)

Phase 1 (foundation) → 2 (retrieval) → 3 (reranking) → 4 (service boundary) →
5 (adapters) → 6 (evaluation) → 7 (benchmark) → 8 (security) → 9 (integration กับ agent-platform) →
10 (production hardening) — ตาม §24 ของ direction doc

Phase 4 ทำไปแล้วบางส่วนในรอบนี้ (service boundary + contract) เพื่อให้ทีมรีวิว boundary ได้ก่อน

⚠️ มี 1 เรื่องที่รอทีมตัดสินใจก่อน Phase 2 จบ:
[#5 Thai full-text search](https://github.com/monthop-gmail/enterprise-knowledge/issues/5)
