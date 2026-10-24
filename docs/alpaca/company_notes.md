# Alpaca — company notes (public sources, Oct 2026)

## Growth
- Revenue reportedly doubled three years running; CEO puts ARR above $100M without detail. API usage grew
  ~4x faster QoQ in Q1 2026 (company press release; usage, not revenue).
- $150M Series D at **$1.15B** (Jan 2026, Drive Capital), then $135M (Jul 2026, Peak XV) at **the same
  $1.15B**. A flat round six months later is a mild negative unless it was an extension; worth asking how
  leadership describes it. Bears directly on option value.
- Headcount ~400–500, up ~50% in a year.

## Hiring mix (Greenhouse board, Oct 23 2026)
69 open roles: **11 product managers, 31 engineers, 27 other** (ops, compliance, settlements, legal, sales).
- PMs: Brokerage EU / UK / Middle East; Clearing Systems; Corporate Actions; Derivatives; Market Data;
  Trading API; Digital Assets Crypto; Digital Assets Tokenization; one Technical PM (infra).
- Nine of eleven are a new geography or a regulated product surface, i.e. owning a rulebook, not a feature roadmap.
- ~22 PMs in seat today → ~33 after this cycle. Against ~200 engineers that is ~1:7, inside the normal band
  (Stripe's PM-light reputation ≈ 1:10–15). The signal to watch is the **growth rate**: PM headcount +50%
  vs engineering +15% in one cycle.
- Tells that the API culture is turning into a bank-with-an-SDK: a PM for the core Trading API, and two
  Project Manager roles (a PMO forming). The one question that settles it: can an engineer change the
  Trading API without a PM signing off?

## Founders
- **CPO (co-founder, ex-CTO):** PostgreSQL window functions (8.4) and CTE work (9.0); Greenplum lead
  architect; Pivotal database kernel. Systems-brained, terse. The executive most likely to want Alpaca to stay
  an API company and to respect a DS who reasons about systems.
- **CEO (co-founder):** Lehman fixed-income securitisation 2005–08; solo trader; co-founded a deep-learning
  computer-vision company (2013) acquired by Kyocera; pivoted Alpaca from ML/market-data shop to licensed
  broker-dealer (2017–18). Instinct-driven, sells well, on record that formal management frameworks limit
  creativity. Opens many fronts (seven countries, crypto, tokenization, derivatives).
- Pairing: instinct CEO + systems CPO is classic. The failure mode is focus, not competence: fronts outrun
  product staffing, PMs get hired in bulk, engineering culture dilutes. Glassdoor (3.6/5, ~53 reviews) names
  senior-level turnover as both symptom and cause.

## Implication for a DS
~33 PMs with blank roadmaps and a small DS team means 6–8 PMs per data scientist and a flood of asks in month
one. Risk: becoming a ticket queue. Opportunity: arrive with a prioritisation frame (revenue at stake ×
decision reversibility) and a self-serve layer for the routine asks, and you are setting direction by day 30.

## Sources
- Greenhouse: https://boards-api.greenhouse.io/v1/boards/alpaca/jobs
- Business Wire (Apr 2026): https://www.businesswire.com/news/home/20260423964388/en/
- Fortune (Jan 2026): https://fortune.com/2026/01/14/alpaca-fundraise-series-d-brokerage-infrastructure/
- Peak XV round (Jul 2026): https://cryptobriefing.com/alpaca-raises-435m-prime-brokerage-ai-trading/
- ODBMS Q&A with the CPO (2018): https://www.odbms.org/2018/03/on-fintech-and-ai-qa-with-hitoshi-harada/
- Fintech Leaders interview with the CEO: https://fintechleaders.substack.com/p/yoshi-yokokawa-ceo-of-alpaca-5-million
- Glassdoor: https://www.glassdoor.com/Reviews/Alpaca-Reviews-E2301035.htm
