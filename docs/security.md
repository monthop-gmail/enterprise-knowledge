# Security

อ้างอิง: §4.2, §4.3, §23 (DoD Security), §26

> **Unauthorized retrieval = failure แม้ answer จะถูกต้อง** (§26)

## ลำดับที่บังคับ

```
Identity → Policy/ACL scope → SQL pre-filter → Dense+Sparse → RRF → Rerank
```

ไม่ใช่

```
Retrieve all → Filter ACL          ❌
```

การถือ row ที่ไม่มีสิทธิ์ไว้ในหน่วยความจำแม้ชั่วครู่ ก็ถือว่า violation แล้ว
`PolicyContext` จึงเป็น **input** ของ retrieval ไม่ใช่ขั้นตอน post-processing

## ScopePredicate

`build_scope_predicate(policy, filters)` คืน SQL fragment + bind params ลำดับความสำคัญ:

1. **Tenant** — `tenant_id = %s` มีเสมอ override ไม่ได้
2. **ACL** — ทุก key ใน `allowed_metadata`: `metadata ->> %s = ANY(%s)`
3. **Caller filters** — `metadata @> %s::jsonb` แคบลงได้อย่างเดียว กว้างขึ้นไม่ได้

**Deny by default:** `metadata ->> key` คืน NULL เมื่อไม่มี key นั้น และ `NULL = ANY(...)` เป็น NULL
ซึ่ง WHERE ถือเป็น false — เอกสารที่ไม่มี key ที่ถูก govern จึงมองไม่เห็นโดยอัตโนมัติ ไม่ต้องเขียนเงื่อนไขเพิ่ม

`allowed_metadata[key] = []` ถูก **reject** ไม่ใช่ ignore — allow-list ว่างแปลว่าปฏิเสธทุกอย่าง
ถ้าไม่ต้องการ govern key นั้นให้ตัด key ทิ้ง

## Tenant boundary เป็น column ไม่ใช่ JSONB key

เบี่ยงจาก field list ตรงตัวใน §8 โดยตั้งใจ: `tenant_id TEXT NOT NULL` เป็นคอลัมน์จริง
เหตุผลคือ §4.3 บอกว่า tenant ต้องเป็น *hard* boundary — JSONB key ลืมใส่ได้ NOT NULL column ลืมไม่ได้
`filters` ที่มี key ใน `RESERVED_METADATA_KEYS` (`tenant_id`, `principal_id`, `_acl`) จะโดน
`TenantBoundaryViolation` ทันที ไม่ใช่ถูกเมิน

## ปฏิเสธ ≠ ไม่เจอ

`PolicyViolation` ต้องถูกโยนออกไป ไม่ใช่คืน list ว่าง
"ไม่มีผลลัพธ์" กับ "คุณไม่มีสิทธิ์ถาม" เป็นคนละคำตอบ และ adapter ต้องคงความต่างนี้ไว้

## Identity มาจาก session ไม่ใช่ tool argument

MCP tool **ห้าม** รับ `tenant_id` เป็น argument — ไม่งั้น agent ตั้ง tenant ให้ตัวเองได้
และ boundary ใน §4.3 จะกลายเป็นแค่คำแนะนำ (Phase 8/9 ต่อกับ identity plane ของ `agent-platform`)

## สถานะตอนนี้

| DoD item (§23) | สถานะ |
|---|---|
| tenant isolation | ✅ contract + tests · Phase 2 ต่อ SQL จริง |
| metadata scope | ✅ contract + tests |
| ACL pre-filter | ✅ อยู่ใน CTE ทั้งสอง (ทดสอบแล้ว) |
| ไม่มี unauthorized leakage | ⏳ ต้องรัน benchmark กับ index จริง (Phase 8) |
| policy context ไม่ถูก bypass | ✅ retriever สร้าง predicate เอง caller ส่งข้ามไม่ได้ |
