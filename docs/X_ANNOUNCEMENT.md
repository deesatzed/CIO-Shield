# CIO-II X (Twitter) Announcement

## Thread (5 posts)

---

### Post 1 (Hook)

We just open-sourced CIO-II — the first macOS app to use Apple's on-device Foundation Model for writing assistance.

It does not generate text. It watches you type, and only when confident, offers a suggestion you accept with Tab or dismiss with Esc.

No cloud. No telemetry. Runs on your Mac's neural engine.

github.com/deesatzed/CIO-II

---

### Post 2 (Differentiator)

Why build this?

Every autocorrect tool has the same failure:
- silently replaces the wrong word
- you notice too late
- trust is gone

CIO-II treats trust as an engineering constraint:
- suggest-only (never silent rewrite)
- hard-blocks in password fields and code editors
- backs off when you dismiss repeatedly
- every change is reversible with undo

---

### Post 3 (Apple FM angle)

The Apple FM model on your chip is used as a constrained arbiter — not a generator.

When there are two plausible corrections and deterministic logic can't decide, Apple FM picks the best one. Or it picks "do nothing."

It has 80ms to decide. If it can't, the answer is always: do nothing.

The model can never invent replacement text. It selects from known candidates only.

---

### Post 4 (Evidence)

What we verified before shipping:
- 331 tests, 94% coverage (no mocks — real SQLite)
- 7 deterministic demo scenarios all pass
- Full mitigation verification: lint, types, security, phrases, schema
- Apple FM arbiter live on macOS 26 + Apple Silicon
- No network calls in core decision path (tested)

---

### Post 5 (CTA)

CIO-II is for Mac users who type a lot and want help without surprises.

Install:
```
git clone https://github.com/deesatzed/CIO-II.git
cd CIO-II && ./bootstrap.sh
./run_demo.sh
```

Then: `cio-ii run --mode mac`

Feedback welcome — tell us where it fails first.

---

## Single-post version (shorter, standalone)

We open-sourced CIO-II — the first macOS app using Apple's on-device Foundation Model for writing assistance.

No cloud. No text generation. Suggest-only with Tab/Esc.

The on-chip FM is a constrained arbiter: it picks from known corrections or does nothing. 80ms timeout. Never invents text.

331 tests. 94% coverage. No mocks.

github.com/deesatzed/CIO-II

---

## Key claims (all verified)

| Claim | Evidence |
|-------|----------|
| First OSS macOS app using Apple FM | python-apple-fm-sdk integration verified live |
| No cloud calls | test_no_network.py passes |
| 331 tests, 94% coverage | pytest output verified |
| Suggest-only default | product contract invariant + demo episode 2 |
| Hard-blocks passwords | demo episode 1 + test_invariants.py |
| FM is selector-only | fm_arbiter.py returns candidate_id or do_nothing only |
| 80ms timeout | fm_arbiter.py timeout config, fail-closed test |
| Backs off on dismissals | trust circuit breaker, demo episode 7 |
| Every change reversible | undo_stack.py + demo episode 5 |

---

## Hashtags (optional)

#macOS #AppleSilicon #AppleIntelligence #OpenSource #AI #WritingTools #Privacy #LocalFirst
