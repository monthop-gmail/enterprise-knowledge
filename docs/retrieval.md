# Retrieval

อ้างอิง: §5, §6, §7, §8, §9, §17

## Stage 1 — candidate retrieval

statement เดียว มี 2 CTE (`build_stage1_sql`) — dense กับ sparse **ต่างก็ถือ scope predicate ตัวเดียวกัน**
ไม่ใช่กรองทีหลัง (§4.2)

```
dense   : embedding <=> %s::vector          (HNSW, cosine)
sparse  : ts_rank_cd(tsv_content, plainto_tsquery('english', %s))
fused   : FULL OUTER JOIN → 1/(rrf_k + dense_rank) + 1/(rrf_k + sparse_rank)
```

`fused` อ่านจาก CTE สองตัวเท่านั้น ไม่ query ตารางซ้ำ — ทดสอบไว้ใน `tests/unit/test_stage1_sql.py`

## RRF เป็น contract ไม่ใช่ implementation detail

```
score(d) = Σ over lists  1 / (rrf_k + rank(d, list))
rank เริ่มที่ 1
```

- เอกสารที่ไม่อยู่ใน list ใด **ได้ 0 จาก list นั้น** ไม่ใช่ "นับเป็นอันดับสุดท้าย"
  ไม่งั้นความยาวของ list จะกลายเป็นน้ำหนักแฝง
- tie-break คงที่: ลำดับที่พบครั้งแรก เรียงตามลำดับ list — ผลลัพธ์ reproducible
- `RRFFuser` (Python) กับสูตรใน SQL ต้องให้ค่าเท่ากัน `tests/unit/test_rrf.py` ตรึงค่าไว้แบบ exact

default (§6): `dense_k=10  sparse_k=10  candidate_k=10  final_k=3  rrf_k=60`

## Stage 2 — cross encoder

FlashRank `ms-marco-TinyBERT-L-2-v2` บน ONNX/CPU
stage 2 **re-sort ของเดิม** เท่านั้น เพิ่มเอกสารใหม่ไม่ได้ → จึงไม่ใช่ security boundary และไม่รับ policy
`RetrievalConfig` บังคับ `final_k <= candidate_k` ตั้งแต่ตอนสร้าง config

`IdentityReranker` ไม่ใช่ "ปิด flag" แต่เป็น arm B ของ benchmark จริง ๆ — ต้องมี path ที่ไม่ rerank ให้เทียบ

## HNSW connection safety (§9)

```
BEGIN
  SET LOCAL hnsw.ef_search = 40
  <vector query>
COMMIT
```

`SET LOCAL` ตายที่ COMMIT — connection ที่คืนเข้า pool จะไม่พก setting ติดไปด้วย
`PostgresStorage.retrieval_transaction()` เป็นทางเดียวที่อนุญาตให้ยิง vector query
**ห้ามเพิ่ม `SET` แบบไม่ LOCAL ที่ไหนก็ตามในคลาสนี้**

`SET LOCAL` รับ bind parameter ไม่ได้ ค่าจึงถูก render ตรง ๆ — ป้องกันด้วย `int()` ไม่ใช่ด้วย driver

### ⚠️ กับดักที่เจอจริงตอนทดสอบกับ PG16 + pgvector

`SET LOCAL` **รั่วได้** ถ้า `conn.transaction()` ไม่ได้เปิด transaction จริง

`psycopg` เปิด implicit transaction ตั้งแต่ statement แรก พอเรียก `conn.transaction()` ทีหลัง
มันจะออกเป็น `SAVEPOINT` ไม่ใช่ `BEGIN` — และการ release savepoint **ไม่** ย้อน `SET LOCAL`
setting จะอยู่ยาวจนกว่า transaction ชั้นนอกจะจบ แปลว่าทุก query หลังจากนั้นบน connection เดียวกัน
วิ่งด้วย `ef_search` ของคนอื่นเงียบ ๆ

วัดจริงแล้วได้:

```
real transaction   :  SET LOCAL 123 → inside 123 → after COMMIT ว่าง       ✅
savepoint (มี txn ค้าง) :  SET LOCAL 123 → after block ยัง 123               ❌ รั่ว
```

อาการนี้ตรวจไม่เจอจาก unit test เพราะผลลัพธ์ยังดู "สมเหตุสมผล" แค่ recall เพี้ยนไป
`PostgresStorage._assert_no_open_transaction()` จึงเช็ค `transaction_status != IDLE` ทุกครั้ง
แล้วโยน `StorageError` — ถูกล็อกไว้ด้วย `tests/integration/test_schema.py` ทั้งสองทิศ
(ทั้งเคสที่ต้องไม่รั่ว และเคสที่พิสูจน์ว่ารั่วจริงถ้าไม่มี guard)

## Latency ต้องแยก (§17)

`dense_ms · sparse_ms · rrf_ms · rerank_ms · retrieval_total_ms · generation_ms · e2e_ms`

ห้ามรายงาน e2e เดี่ยว ๆ แล้วสรุปว่า engine เร็วหรือช้า และห้ามบวก generation เข้า retrieval (§25)

## ข้อควรรู้: FTS เป็น `english`

`tsv_content` ใช้ `to_tsvector('english', content)` ตาม §8 ตรงตัว
ถ้า corpus จริงเป็นภาษาไทย stemming ของ `english` จะไม่ช่วยอะไร และ PostgreSQL ไม่มี Thai config มาให้
ทางเลือกตอนถึง Phase 2: เพิ่ม column `tsv_content_simple` ด้วย config `simple` + ตัดคำไทยก่อน index
**ยังไม่แก้ในรอบนี้** เพราะเป็นการเปลี่ยน canonical schema — ต้องให้ทีมตัดสินใจก่อน
