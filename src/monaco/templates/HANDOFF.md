# HANDOFF — <Company> Take-Home · Continue in fresh session

**Read this whole file first.** The discipline that matters most: **never hand-write a number into prose
or a chart caption — compute it first, then quote it.** Every number below must be verified against the
data before it lands here.

## 1 · Project & deliverable

<One paragraph: the prompt, the data files (paths + row/entity counts), what the deliverable is and which
script builds it end-to-end. State where the builder lives and how to run it.>

**Build gotchas (standing):** report HTML body is one giant f-string (double literal braces); notebook
builder cells are non-f strings (escape \n and \$ instead); HTML comments cannot nest (stash sections as
plain strings); escape `<` as `&lt;` in anything routed to raw HTML; `assert anchor in t` before every
`t.replace(...)`; after each build verify figure count, brace-leak regex, and Read one extracted PNG.

## 2 · Core definitions (exact)

<Every metric and tier definition, exactly. Entity grain of each table. Windows and cutoffs.>

## 3 · Verified numbers (safe to quote)

| Stat | Value |
|---|---|
| <stat> | <value> |

## 4 · Style rules

Voice: GM-concise, pyramid, answer-first; no em-dashes in body prose. Palette and chart grammar:
`monaco.viz` + PLAYBOOK. Penetration horizontal / distribution vertical with the two fixed labels.
Naming: "total GMV", "GMV per X" — never "avg"/"lifetime" variants.

## 5 · Current document structure

<Section-by-section map of the deliverable as it stands, including what is HIDDEN and how to restore.>

## 6 · TASK LIST

<Numbered, with done/open status. Mark decisions that are the interviewer's/user's to make.>

## 7 · Live-review prep

<The derivations that must be recallable cold. The AI-usage disclosure draft.>

## Session updates

<Append a dated block per working session: what changed, new verified numbers, new gotchas hit.>
