---
name: takehome-handoff
description: Write or refresh the take-home's HANDOFF.md state document — verified numbers, style rules, task list, session log, live-review prep — so any fresh session can continue cheaply. Use at the end of every working session or before switching machines/sessions.
user-invocable: true
---

# /takehome-handoff — session continuity

The HANDOFF.md pattern is what made the Faire take-home survivable across many sessions: one state
document that a fresh session reads first and trusts completely. Template:
`src/monaco/templates/HANDOFF.md`.

## When invoked
1. If `docs/HANDOFF.md` doesn't exist in the current company folder, create it from the template.
2. Otherwise refresh it:
   - **§3 Verified numbers**: add every number newly computed this session (and only computed ones).
     Correct any that changed; a stale number in HANDOFF is worse than none.
   - **§5 Document structure**: update the section map, including what is HIDDEN and how to restore it.
   - **§6 Task list**: mark done items, add new ones, flag decisions that belong to the user.
   - **Session updates**: append a dated block — what changed, gotchas hit (these graduate to
     docs/PLAYBOOK.md if general), decisions made and by whom.
3. Keep the standing build-gotchas paragraph intact — it is the accumulated trap list.
4. Maintain **§7 Live-review prep**: the derivations the user must produce cold in a live review
   (definitions, headline EVs and both corroboration routes, haircut rationale, selection-effect
   defenses), plus the AI-usage disclosure draft — a deliverable, not an afterthought.

## Rules
- The handoff states facts, not narrative. GM-concise.
- Numbers only from this session's computed output; each new claim must be reproducible from a named
  script or notebook.
- If the same clarifying question has come up twice across sessions, its answer belongs here (or in
  PLAYBOOK if cross-company).
