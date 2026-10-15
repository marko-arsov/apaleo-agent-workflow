# API enum wire values

Default for **new or changed** JSON / OpenAPI enums on Apaleo APIs:

- Serialize the **C# enum member name** (PascalCase) — the same tokens `StringEnumConverter` already emits elsewhere (`ConcertsAndMusic`, `Daily`, `LocalTax`).
- **Display labels belong on the UI** (`"Concerts & Music"`), not on the wire.
- Protocol encodings (iCalendar `FREQ=DAILY`, ISO codes, …) belong in **internal translators**, not on public JSON, unless that protocol *is* the consumer contract.

Do **not** add a dedicated `JsonConverter` or Swashbuckle schema filter just to emit human-readable strings. If wire values already match the CLR names, Swashbuckle’s default enum schema is enough.

This is an **unstable-API** default too (`v0-nsfw`). Pretty RFC samples are not a reason to copy display text onto the contract.

## Specify (mandatory question)

When the ticket **adds or changes** an API enum (request/response JSON, swagger examples, generated proxies):

Ask **one** A/B question and **stop until the user answers**. Recommend **A** even if Linear, an RFC, or a sample payload uses display text.

```
N. Enum JSON on the API — recommended A
   A — Machine-readable member names (`ConcertsAndMusic`, `Daily`). UI maps display labels. No custom converter.
   B — Custom wire strings (RFC display names, iCalendar FREQ, …). Only if a cited consumer needs those exact tokens. Plan must include the C# ↔ JSON table.
```

- Counts toward specify’s question budget when relevant; **skip entirely** if the ticket has no API enums.
- Ask even in **lean** specify (estimate ≤2). Copying RFC labels onto the wire without asking is the failure this rule exists to catch.
- RFC / Notion samples with pretty labels are **not** sufficient to pick B.

Record the answer as a Key Decision (`D#`) plus the Contracts table (C# ↔ JSON).

## Implement / review

- Follow the locked `D#`. Custom display-string converters are a **defect** unless that decision chose B.
- If the plan is silent and you are about to invent display-string wire values → stop and ask; do not default to RFC prose.
