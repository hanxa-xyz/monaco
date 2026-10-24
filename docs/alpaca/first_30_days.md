# First 30 days — Senior Product DS, Broker API

Order of introductions, by who grades the work and who controls data access. Thirty minutes each; talk 20%.
Three questions every time: *what do you own · what decision is blocked on data · who else should I meet*.
The third question grows the list without guessing.

## Week 1 — the people who grade you
- **Manager (Head of AE & DS).** Ask for the leveling criteria conversation explicitly and early: what would
  "bordering staff" look like by month six. Ask for her three most important stakeholders; that is the intro list.
- **Director of Data.** Ask what the last DS recommendation that *didn't* make the roadmap was, and why. That is
  the map of the friction.
- **DS teammates.** Who owns what, which tables to trust, which PMs are partners and which ones generate tickets.
- **Analytics engineers.** They are the pipeline; you need them more than they need you.

## Week 2 — the Broker API surface
- **Broker API PM(s), Trading API PM.** "What decision are you trying to make this quarter that you don't have
  the numbers for?" Write the answers down; that is the first-90-days backlog.
- **Broker API tech lead.** Where events are emitted, what is instrumented, what isn't. Also the culture
  question: can an engineer change the API without a PM signing off?
- **Partner success / customer experience lead.** Partner health is the core DS surface in B2B2C; this person sits on the signal.
- **Sales / BD lead for the region.** What partners ask before signing; what churned partners said on the way out.

## Weeks 3–4 — the edges and the top
- **Data Platform lead.** Infra roadmap, self-serve, warehouse access without a ticket.
- **One ops/compliance person on the Broker API side.** Half the "product" questions in a self-clearing broker
  are ops questions.
- **FP&A partner.** How revenue is recognised per partner. Nothing can be sized without this.
- **CPO (co-founder, ex-Postgres kernel engineer).** 20-minute skip-level. Don't pitch; ask one systems question
  about how he thinks about Broker API metrics.

## Running doc
Keep one list of every "we don't know X" heard in these meetings. By day 30 there will be ~10 candidate
projects ranked by how many people said the same thing. Pick the one two PMs and the Director all mentioned.
That is the first deliverable and the first staff-level story.

Skip the audit questions from the interview loop ("% of DS recs on the roadmap"); the answer is known. The
job is to change it, not measure it.
