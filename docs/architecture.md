# Kotoba Backend — Architecture

## 1. Request lifecycle

Every spoken turn goes through a single pipeline in `ConversationOrchestrationService.process_turn`:

```
audio bytes + lesson_id + user_id (JWT)
        │
        ├─[parallel]─ get_lesson()          → Supabase Storage (cached in-process)
        │             get_history()          → Redis key conv:{uid}:{lid}
        │             get_current_state()    → Redis key step:{uid}:{lid} → Supabase fallback
        │
        ├─ _transcribe()                     → Groq Whisper (20s timeout)
        │
        ├─ generate_response()               → Groq LLM + step context injected into prompt
        │
        ├─ update_after_turn()               → Redis (write) + Supabase upsert (write)
        │
        ├─ get_next_lesson_id() [if done]    → Supabase modules table
        │
        ├─ synthesize()                      → Groq TTS → Supabase Storage upload
        │
        └─ append_turn()                     → Redis key conv:{uid}:{lid}
```

---

## 2. Decision engine — 6-step progression (K-05.1)

The pedagogical progression follows 6 steps. `DecisionEngineService` is the single source of truth for which step a user is on.

### State shape (`StepState`)

```python
class StepState(TypedDict):
    current_step: int        # 1–6
    turns_on_step: int       # resets to 0 when step advances
    consecutive_errors: int  # resets to 0 on a correct turn
    completed: bool          # True when step 6 is done
```

### Progression rules

| Condition | Action |
|---|---|
| Turn has no error AND `turns_on_step + 1 < _TURNS_TO_ADVANCE (2)` | Increment `turns_on_step`, reset `consecutive_errors` |
| Turn has no error AND `turns_on_step + 1 >= 2` AND `step < 6` | Advance `current_step`, reset `turns_on_step` to 0 |
| Turn has no error AND `turns_on_step + 1 >= 2` AND `step == 6` | Set `completed = True` |
| Turn has error | Increment `consecutive_errors` and `turns_on_step` (no advancement) |

### Step context injected into LLM

```
"Current step: 3/6. Turns on step: 1. Consecutive errors: 0."
```

The pedagogical agent uses this to modulate its behavior (e.g., be more corrective on repeated errors, advance vocabulary on step changes).

---

## 3. Progress persistence — write-through cache (K-06.2)

Progress is persisted in two layers with different trade-offs.

### Layer 1: Redis — hot cache

- **Key:** `step:{user_id}:{lesson_id}`
- **TTL:** 24 hours (matches conversation history expiry)
- **Content:** full `StepState` as JSON
- **Access:** every turn reads here first

### Layer 2: Supabase — durable store

- **Table:** `user_progress`
- **Columns:** `user_id`, `lesson_id`, `current_step`, `status` (`not_started` | `in_progress` | `completed`), `updated_at`
- **Access:** read only on Redis cold-start; written on every turn

### Cold-start recovery

When Redis has no entry (e.g., TTL expired, new instance, server restart), `get_current_state` falls back to Supabase:

```
Redis miss → Supabase query
  → row found: StepState(current_step=row.current_step, turns_on_step=0, consecutive_errors=0)
  → no row:    StepState(current_step=1, turns_on_step=0, consecutive_errors=0)
```

`turns_on_step` and `consecutive_errors` are not persisted in Supabase — they are in-session state. On a cold start they reset to 0, which is acceptable: the student needs at most 2 turns to re-confirm their step before advancing.

---

## 3b. Student model — vocabulary, errors & BKT (K-06.1)

Per (user, lesson) pedagogical state, updated once per turn from the agent's
`razonamiento`. Three dimensions

### Persistence

- **Redis:** `student:{user_id}:{lesson_id}`, TTL 24h — active session copy.
- **Supabase:** `student_models` table (migration 008), upsert on every turn — durable mirror.
- **Cold start:** Redis miss → Supabase read → Redis rehydrated.

### Update flow (per turn)

1. `ConversationOrchestrationService` loads the model and injects a compact
   `contexto_estudiante` string into the agent prompt (mastery, frequent error
   categories, struggling vocabulary).
2. After the agent responds, `StudentModelService.update_after_turn` classifies
   the detected error (`categoria_error` from the LLM, keyword fallback),
   updates vocabulary exposures and applies one BKT step
   (`correct = no error_detectado`).
3. System errors (invalid LLM JSON) skip the update — they say nothing about
   the student. Any internal failure is logged and swallowed: the student
   model can never break `/turn`.

### BKT parameters (v1)

`P(L0)=0.2`, `P(T)=0.15`, `P(S)=0.10`, `P(G)=0.15`. Mastery levels:
`introducing` (P(L) < 0.5), `practicing` (0.5–0.95), `mastered` (>= 0.95).

---

## 4. Multi-lesson module progression (K-05.2)

### Module structure

The `modules` table stores ordered lesson sequences:

```sql
CREATE TABLE public.modules (
    id         uuid PRIMARY KEY,
    title      varchar(200),
    language   varchar(10),
    level      varchar(2),   -- A1, A2, B1, B2, C1, C2
    lesson_ids uuid[],        -- ordered lesson sequence
    is_active  boolean
);
```

A GIN index on `lesson_ids` makes `cs` (contains) queries fast even with large arrays.

### Resolution logic

`ModuleRepository.get_next_lesson_id(lesson_id)`:
1. Query `modules` where `lesson_ids @> ARRAY[lesson_id]` and `is_active = true`.
2. Find `lesson_id`'s index in the array.
3. Return `lesson_ids[idx + 1]`, or `None` if it's the last element.

### Response contract

The `/v1/conversation/turn` response always includes:

```json
{
  "lesson_completed": false,
  "next_lesson_id": null
}
```

`lesson_completed` becomes `true` only in the exact turn that completes step 6. `next_lesson_id` is populated only when `lesson_completed == true` AND there is a subsequent lesson in the module.

The Flutter client is responsible for routing: when `lesson_completed == true`, it shows a completion screen; if `next_lesson_id != null`, it offers to start the next lesson.

---

## 5. Data stores summary

| Store | Technology | Purpose | Key pattern |
|---|---|---|---|
| Lesson content | Supabase Storage | JSON files per lesson (immutable) | bucket path |
| TTS audio | Supabase Storage | Generated MP3/audio per turn | bucket path |
| User progress | Supabase PostgreSQL | Durable step state | `user_progress(user_id, lesson_id)` |
| Module definitions | Supabase PostgreSQL | Ordered lesson sequences | `modules` table |
| Step state cache | Upstash Redis | Hot in-session state | `step:{uid}:{lid}` |
| Student model | Supabase PostgreSQL | Durable vocabulary/errors/BKT | `student_models(user_id, lesson_id)` |
| Student model cache | Upstash Redis | Hot in-session model | `student:{uid}:{lid}` |
| Conversation history | Upstash Redis | LLM context window | `conv:{uid}:{lid}` |

---

## 6. Resilience notes

- **Redis unavailable on read (conversation history):** fallback to empty history; turn still completes.
- **Redis unavailable on write (turn or step state):** logged as warning; Supabase write still happens for step state.
- **Supabase unavailable for step state:** Redis cache serves the state if warm; if both unavailable the turn will error.
- **Groq ASR timeout (20s):** returns HTTP 502 to the client.
- **TTS failure:** `audio_url` returns `null`; the client falls back to text-only display.
- **Student model failure (Redis or Supabase):** logged as warning and skipped; the turn always completes.
