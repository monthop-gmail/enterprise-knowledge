# Security

อ้างอิง: §4.2, §4.3, §23 (DoD Security), §26

> **Unauthorized retrieval = failure แม้ answer จะถูกต้อง** (§26)

## สองชั้น ต่างกันที่ "ข้ามได้ไหมถ้ามีคนอนุญาต" ไม่ใช่ "เข้มแค่ไหน"

[ADR-0021](https://github.com/monthop-gmail/agent-platform/blob/main/decisions/0021-workspace-is-a-scope-not-a-boundary.md)

| | `tenant_id` | `workspace_id` |
|---|---|---|
| ข้ามได้ไหม | **ไม่ได้ทุกกรณี** ไม่มี policy/consent/admin คนไหนอนุญาตได้ | **deny by default แต่อนุญาตได้** ผ่าน policy |
| บังคับที่ชั้นไหน | ชั้นเก็บข้อมูล | ชั้นตรวจสิทธิ์ |
| แอปเขียนผิด | ยังข้ามไม่ได้ | รั่วได้ → ต้องมีเทสครอบ |
| ข้ามสำเร็จ | ไม่มีทาง | **ต้องระบุได้ว่าอนุญาตด้วยอะไร** |

> ถ้า cross-workspace ทำได้เงียบ ๆ มันก็ไม่ต่างจากไม่มี workspace เลย

`CrossWorkspaceGrant` จึง**บังคับต้องมี `policy_decision_id`** — ขยาย scope โดยไม่ระบุว่าใครอนุญาต
สร้าง object ไม่ได้ตั้งแต่แรก ไม่ใช่ lint warning · การยิง audit event จริงต้องรอ `event/v1` (Phase 9 · #17 #25)
แต่ *เงื่อนไขก่อนหน้า* บังคับได้ตั้งแต่ตอนนี้ — จะไม่มีการข้ามที่เกิดวันนี้แล้วสืบกลับไม่ได้ทีหลัง

`department` เป็น **label ของ workspace** (ADR-0007) ไม่ใช่ชั้นแบ่งข้อมูล — metadata filter ที่ลอยอยู่
โดยไม่มี workspace คือชั้นที่สามที่ ADR ห้ามไว้ ในชื่ออื่น

## ลำดับที่บังคับ

```
Identity → Policy scope (tenant + workspace + ACL) → SQL pre-filter → Dense+Sparse → RRF → Rerank
```

ไม่ใช่

```
Retrieve all → Filter ACL          ❌
```

การถือ row ที่ไม่มีสิทธิ์ไว้ในหน่วยความจำแม้ชั่วครู่ ก็ถือว่า violation แล้ว
`PolicyContext` จึงเป็น **input** ของ retrieval ไม่ใช่ขั้นตอน post-processing

## ScopePredicate

`build_scope_predicate(policy, filters)` คืน SQL fragment + bind params ลำดับความสำคัญ:

1. **Tenant** — `tenant_id = %s` มีเสมอ override ไม่ได้ และ grant ใดก็ขยายไม่ได้
2. **Workspace** — `workspace_id = ANY(%s)` · list มีแค่ workspace ตัวเองจนกว่าจะมี `CrossWorkspaceGrant`
   deny-by-default จึงอยู่ใน **เนื้อของ list ไม่ใช่รูปของ SQL** — ค้นแบบแคบกับแบบกว้างใช้ statement เดียวกัน
   ไม่มี code path ที่สองให้เขียนพลาด
3. **ACL** — ทุก key ใน `allowed_metadata`: `metadata ->> %s = ANY(%s)`
4. **Caller filters** — `metadata @> %s::jsonb` แคบลงได้อย่างเดียว · `department` อยู่ชั้นนี้

**Deny by default:** `metadata ->> key` คืน NULL เมื่อไม่มี key นั้น และ `NULL = ANY(...)` เป็น NULL
ซึ่ง WHERE ถือเป็น false — เอกสารที่ไม่มี key ที่ถูก govern จึงมองไม่เห็นโดยอัตโนมัติ ไม่ต้องเขียนเงื่อนไขเพิ่ม

`allowed_metadata[key] = []` ถูก **reject** ไม่ใช่ ignore — allow-list ว่างแปลว่าปฏิเสธทุกอย่าง
ถ้าไม่ต้องการ govern key นั้นให้ตัด key ทิ้ง

## Tenant boundary เป็น column ไม่ใช่ JSONB key

เบี่ยงจาก field list ตรงตัวใน §8 โดยตั้งใจ: `tenant_id TEXT NOT NULL` เป็นคอลัมน์จริง
เหตุผลคือ §4.3 บอกว่า tenant ต้องเป็น *hard* boundary — JSONB key ลืมใส่ได้ NOT NULL column ลืมไม่ได้
`filters` ที่มี key ใน `RESERVED_METADATA_KEYS` (`tenant_id`, `workspace_id`, `principal_id`, `_acl`)
จะโดน `TenantBoundaryViolation` ทันที ไม่ใช่ถูกเมิน — `workspace_id` อยู่ในนั้นด้วยเหตุผลเดียวกับ
`tenant_id` คือ caller ที่ตั้ง workspace ให้ตัวเองผ่าน filter ได้ = ข้าม policy decision ที่ควรเป็นคนอนุญาต

## ปฏิเสธ ≠ ไม่เจอ

`PolicyViolation` ต้องถูกโยนออกไป ไม่ใช่คืน list ว่าง
"ไม่มีผลลัพธ์" กับ "คุณไม่มีสิทธิ์ถาม" เป็นคนละคำตอบ และ adapter ต้องคงความต่างนี้ไว้

## Identity มาจาก session ไม่ใช่ tool argument

MCP tool **ห้าม** รับ `tenant_id` เป็น argument — ไม่งั้น agent ตั้ง tenant ให้ตัวเองได้
และ boundary ใน §4.3 จะกลายเป็นแค่คำแนะนำ (Phase 8/9 ต่อกับ identity plane ของ `agent-platform`)

## สถานะตอนนี้

| DoD item (§23) | สถานะ |
|---|---|
| tenant isolation | ✅ contract + tests · ตรวจกับ index จริงแล้ว |
| workspace scope (ADR-0021) | ✅ deny-by-default + grant · 7 ground-truth case ผ่านกับ DB จริง |
| metadata scope | ✅ contract + tests |
| ACL pre-filter | ✅ อยู่ใน CTE ทั้งสอง (ทดสอบแล้ว) |
| ไม่มี unauthorized leakage | ⏳ ต้องรัน benchmark กับ index จริง (Phase 8) |
| policy context ไม่ถูก bypass | ✅ retriever สร้าง predicate เอง caller ส่งข้ามไม่ได้ |
