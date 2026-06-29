# Provenance_Guard

AI content attribution API. Accepts text submissions, runs two detection signals (Groq LLM + stylometric heuristics), returns a structured confidence score and transparency label. Supports appeals and a queryable audit log.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # add GROQ_API_KEY
python app.py         # runs on port 5001
```

## Endpoints

| Method | Path | Description |
|---|---|---|
| POST | `/submit` | Submit text for classification |
| POST | `/appeal` | Appeal a classification decision |
| GET | `/log` | Retrieve recent audit log entries |

---

## Architecture Overview

A submission follows this path:

1. **Flask router** receives `POST /submit` with `text` and `creator_id`
2. **Flask-Limiter** checks IP rate limits — rejects with 429 if exceeded
3. **Detection pipeline** (`detection/pipeline.py`) runs two independent signals on the raw text:
   - **Signal 1**: Groq LLM classifier — sends text to `llama-3.3-70b-versatile`, gets back `ai_probability`
   - **Signal 2**: Stylometric heuristics — computes 5 surface-level statistical features
4. **Ensemble combiner** merges scores: `confidence = groq × 0.60 + stylo × 0.40`
5. **Label builder** (`labels.py`) maps confidence score to one of 3 transparency label variants
6. **Audit logger** (`db.py`) writes a structured SQLite record — content hash, both signal scores, label, status
7. **Response** returns `content_id`, `attribution`, `confidence`, `signals`, `label`, `timestamp`

---

## Detection Signals

### Signal 1 — Groq LLM Classifier

**What it measures:** Semantic and structural patterns — fluency, coherence, characteristic LLM phrasing, and topic consistency. The model has internalized what AI-generated prose looks like across a huge range of examples and acts as a semantic judge.

**Why I chose it:** Stylometric features see the surface; LLMs see meaning. A sentence with high burstiness can still be semantically "too smooth." Groq's free tier makes this zero-cost in development. Weight: **60%** — it's the stronger signal for most inputs.

**What it misses:** Deliberately imperfect AI output (instructed to add typos, vary sentence length). Highly technical human writing (documentation, academic abstracts) where humans *should* sound uniform. Non-native English writers whose writing is more formal than typical. No memory of the author's baseline style.

---

### Signal 2 — Stylometric Heuristics

**What it measures:** Five surface-level statistical features:
1. **Sentence length burstiness** — std dev of sentence lengths; AI is uniform, humans are bursty
2. **Average sentence length** — AI clusters around 15–25 words; extremes are human-like
3. **Type-token ratio (TTR)** — vocabulary diversity; AI on a topic reuses vocabulary
4. **AI function word density** — "however," "furthermore," "consequently" appear at elevated rates in AI writing
5. **Punctuation consistency** — AI ends most sentences with periods; human writers mix in `?`, `!`, `—`

**Why I chose it:** Pure Python, zero external dependencies, runs offline. Gives a fast baseline even when Groq is unavailable. Computationally interpretable — each feature score is inspectable.

**What it misses:** Short texts (< 100 words) — TTR and burstiness are unreliable below ~150 tokens. Professionally edited human writing looks AI-like on surface statistics. Deliberately sloppy AI output defeats it entirely.

---

## Confidence Scoring

**Formula:** `confidence = groq_score × 0.60 + stylometric_score × 0.40`

Groq gets 60% weight because it operates at the semantic level, which is harder to spoof and more generalizable. Stylometrics gets 40% as a fast, interpretable corroborating signal.

**Fallback:** If Groq is unavailable, full weight goes to stylometric score.

**Validation:** Tested on 4 deliberately chosen inputs — all scores matched intuition:

| Input | Groq | Stylo | Ensemble | Label |
|---|---|---|---|---|
| Clearly AI (formal, connectives) | 0.88 | 0.578 | **0.759** → `ai` | 76% AI |
| Clearly human (casual, irregular) | 0.07 | 0.246 | **0.140** → `human` | 86% human |
| Borderline formal human | 0.45 | 0.403 | **0.431** → `uncertain` | 43% uncertain |
| Lightly edited AI | 0.58 | 0.448 | **0.527** → `uncertain` | 53% uncertain |

**Two example submissions with noticeably different confidence scores:**

**High-confidence (score: 0.74 → `ai`):**
> *"Artificial intelligence has fundamentally transformed the landscape of modern technology. Furthermore, the implications of machine learning extend far beyond conventional computing paradigms. Moreover, these systems demonstrate remarkable capabilities..."*

**Lower-confidence (score: 0.64 → `uncertain`):**
> *"The relationship between monetary policy and asset price inflation has been extensively studied in the literature. Central banks face a fundamental tension between their mandate for price stability..."*

The second is formally written human text — Groq hedges (0.80) but the stylometric score is lower (0.40), and the ensemble lands in the uncertain band.

---

## Transparency Labels

All three variants are reachable and return different text:

**`ai` — score ≥ 0.70:**
> Headline: **Likely AI-Generated**
> Body: "Our system is highly confident this content was AI-generated (confidence: 74%). This content has been labeled accordingly. If you are the author and believe this is incorrect, you may submit an appeal."
> Display: "74% AI likelihood"

**`human` — score ≤ 0.30:**
> Headline: **Likely Human-Written**
> Body: "Our system is highly confident this content was written by a human (confidence: 78% human likelihood). No AI attribution label has been applied."
> Display: "78% human likelihood"

**`uncertain` — score 0.31–0.69:**
> Headline: **Authorship Uncertain**
> Body: "Our system found mixed signals in this content and cannot confidently determine authorship (64% AI likelihood). No definitive label has been applied. If this is your original work, you may submit an appeal to have it reviewed."
> Display: "64% AI likelihood (uncertain)"

The uncertain band is intentionally wide (0.31–0.69). Better to under-label than to falsely accuse a human author.

---

## Rate Limiting

| Endpoint | Limit | Reasoning |
|---|---|---|
| `POST /submit` | 10/minute, 100/day | A writer submitting their own work needs at most 1–2/min. 10/min stops scripted flooding while staying invisible to legitimate use. 100/day maps to Groq free-tier API capacity. |
| `POST /appeal` | 5/hour | Appeals require human review. 5/hour is generous for legitimate disputes; prevents appeal-flooding by bad actors. |

### Evidence

```bash
for i in $(seq 1 12); do
  curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost:5001/submit \
    -H "Content-Type: application/json" \
    -d '{"text": "This is a test submission for rate limit testing purposes only, ensuring minimum length.", "creator_id": "ratelimit-test"}'
done
```

Output (12 rapid requests against 10/minute limit):

```
200
200
200
200
200
200
200
200
200
200
429
429
```

First 10 succeed; requests 11–12 return `429 Too Many Requests`.

---

## Audit Log

Every `/submit` call writes a structured SQLite record. Retrieve with `GET /log`.

Example entry with appeal filed:

```json
{
  "content_id": "a2d4c497-de88-49a9-b1d3-0a5e402a24db",
  "creator_id": "demo-user-3",
  "timestamp": "2026-06-26T01:36:12.000Z",
  "attribution": "uncertain",
  "confidence": 0.641,
  "llm_score": 0.8,
  "signals": { "groq": 0.8, "stylometric": 0.4026 },
  "status": "under_review",
  "appeal": {
    "creator_reasoning": "I am an economics researcher. This is my own writing from a policy memo I authored.",
    "timestamp": "2026-06-26T01:36:45.000Z"
  }
}
```

---

## Known Limitations

**Professionally edited human writing will score as uncertain or AI.** A polished essay with logical transitions, consistent paragraph length, and formal vocabulary is statistically indistinguishable from AI output on both signals. The Groq classifier finds it "suspiciously coherent"; stylometrics sees low burstiness and elevated function word density. The system correctly refuses to label it AI (landing in `uncertain`), but the score will be misleadingly high for the author. This is a fundamental limitation: the features that distinguish AI writing are also the features of *good* writing.

---

## Spec Reflection

**One way the spec helped:** Writing out the false positive scenario in planning.md before building forced a concrete design decision — make the uncertain band wide (0.31–0.69, not 0.40–0.60) and make the appeal flow low-friction. Without that analysis, I would have set tighter thresholds and built the appeal endpoint as an afterthought.

**One way implementation diverged:** The spec defined the endpoint as `POST /appeal/<content_id>` with `content_id` in the URL path. The assignment's test instructions used `POST /appeal` with `content_id` in the request body. I kept both routes working — the path-based version for REST correctness, the body-based version for compatibility with the test harness. The spec didn't anticipate this mismatch.

---

## AI Usage

**Instance 1 — Stylometric scoring functions:** I prompted Claude to implement the five stylometric feature functions using my planning.md signal descriptions as the spec. It generated reasonable implementations for burstiness and TTR, but the function word density normalizer (`density / 0.04`) was tuned to an arbitrary threshold I hadn't defined. I revised the threshold to `0.04` (4% density = notably AI-like) based on reading the actual word lists, not the generated default.

**Instance 2 — Confidence threshold selection:** I asked Claude to verify that the generated label thresholds matched my planning.md spec. It caught that the initial thresholds (`>=0.80` AI, `<=0.25` human) were too conservative — the AI text test case scored 0.754 and landed `uncertain` instead of `ai`. I overrode to `>=0.70` / `<=0.30`, which correctly classified all four test inputs while keeping the uncertain band wide enough to protect against false positives.
