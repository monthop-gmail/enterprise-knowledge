# Evaluation

อ้างอิง: §15, §16, §17, §18, §19, §25

Evaluation เป็น **capability ระดับเดียวกับ retrieval** ไม่ใช่ script สาธิต (§15)
§25 ห้าม benchmark ที่ไม่มี ground truth และห้าม benchmark ที่ต้องยิง LLM ทุกครั้ง

## Ground truth

`evaluation/ground_truth.py` — corpus 5 เอกสาร 2 tenant, 4 case

แต่ละ case มีทั้ง `expected_document_ids` และ `expected_denied_document_ids`
เพราะการได้คำตอบถูกจาก scope ที่ผิดคือ security failure ไม่ใช่ "ถูกบางส่วน" (§26)

corpus ออกแบบให้ 2 tenant **ใช้คำศัพท์ทับกัน** ("annual leave") โดยตั้งใจ — ถ้า tenant filter พัง
มันจะโผล่เป็น leak ไม่ใช่เป็น miss เงียบ ๆ

## Metrics

| metric | ความหมาย | หมายเหตุ |
|---|---|---|
| `Hit@K` | มี expected doc ใน top-k ไหม | 0/1 |
| `Recall@K` | สัดส่วน expected doc ที่เจอ | expected ว่าง → 0.0 ไม่ใช่ 1.0 |
| `MRR` | 1/อันดับของ hit แรก | เฉลี่ยทุก case |
| `metadata_leakage` | นับผลลัพธ์ที่ scope ไม่ควรให้เห็น | **gate ไม่ใช่ score** |
| `p50 / p95` | latency แยกตาม stage | §17 |

`leakage > 0` = fail ทั้ง run ไม่ว่าตัวเลขคุณภาพจะสวยแค่ไหน (`ArmResult.passed`)

## Benchmark matrix (§16)

ทุก case ต้องผ่านครบ 3 arm:

```
A. dense           RetrievalStrategy.DENSE
B. hybrid + RRF    RetrievalStrategy.HYBRID
C. B + FlashRank   RetrievalStrategy.HYBRID_RERANK
```

เทียบ B กับ C คือหัวใจ — เป็นวิธีเดียวที่พิสูจน์ว่า reranker คุ้มกับ latency ที่จ่ายไป

## Offline vs integration (§18)

| | offline | integration |
|---|---|---|
| corpus | fixture ใน repo | PostgreSQL + pgvector จริง |
| embedder | `DeterministicEmbedder` | OpenAI `text-embedding-3-small` |
| reranker | identity | FlashRank จริง |
| MCP | ไม่เกี่ยว | session จริงผ่าน stdio |
| ใช้ตอน | CI ทุก commit | ก่อน release / tuning |
| ค่าใช้จ่าย | 0 | API + เวลา |

> ⚠️ ตัวเลข offline เทียบได้กับ offline ด้วยกันเท่านั้น
> `DeterministicEmbedder` เป็น hash ไม่มี semantic — Hit@K ของมันบอกคุณภาพ retrieval จริงไม่ได้
> ใช้สำหรับจับ regression ของ *อัลกอริทึม* (RRF, scope, ordering) เท่านั้น

## MCP functional test (§19)

เรียก Python function ตรง ๆ **ไม่นับเป็น MCP test**
ต้อง spawn server จริง → initialize → list tools → call → validate → ตรวจ stdout → shutdown
ข้อที่จับ bug ได้จริงคือ **stdout integrity**: `print()` หลงเหลือหนึ่งบรรทัดก็ทำ JSON-RPC พังแล้ว
และ unit test จับไม่ได้เลย

## ลำดับการ optimize (§26)

```
Correctness → Security → Evaluation → Baseline → Performance → Scale
```

ห้าม tune HNSW ก่อนมี baseline (§25)
