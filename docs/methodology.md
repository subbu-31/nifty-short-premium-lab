# Methodology: bugs found, and how they were caught

This is the part of the project most worth reading even if you don't care
about NIFTY options specifically. Every one of these was caught *by
building the specific test that could kill it*, not by inspection.

## 1. Look-ahead bias in a volatility-regime classifier

**Symptom:** a first-pass test (volume-weighted strike/spot ratio vs.
next-day return) classified each day into a quintile using
`np.percentile()` over the *entire* dataset — meaning day 10's bucket
assignment depended on data from day 500.

**Fix:** rebuilt as a walk-forward classifier (`pipeline/signals/walkforward.py`)
that only ever ranks a day against the expanding history strictly before it.
The first `min_history` days are unclassifiable and correctly dropped, not
filled with a biased guess.

**Test that would catch a regression:** `tests/test_walkforward.py` includes
an adversarial check — classify the same series twice, once with a normal
tail and once with the tail replaced by extreme outliers, and assert every
classification of a date *before* the tail is identical in both runs. If
it isn't, the classifier is peeking forward.

## 2. A unit-convention bug that looked like data corruption

**Symptom:** aggregate daily option volume computed to *billions* of
contracts — physically impossible (real NSE volume tops out in the tens of
millions on a heavy day).

**Diagnosis, not assumption:** rather than discard the volume field as
corrupted, tested a hypothesis — the raw values are in *shares*, not
*lots* — by checking what fraction of raw values divided cleanly by
candidate lot sizes (25/50/65/75) across the full date range. Found >97%
divisibility by 75 for early-dataset contracts and by 65 for later ones,
with a clean single transition at the 2026-01-06 expiry — a real NSE
lot-size revision, not noise. The conversion factor is a property of the
*contract*, not the *calendar date*: existing contracts keep their
original lot size for life, only newly-listed contracts adopt a change.

**Lesson:** an implausible aggregate is a hypothesis-generation exercise,
not necessarily corruption. "Divide by a discoverable, empirically-testable
factor" beat "discard the field."

## 3. Timezone/session-boundary contamination in a cross-market signal

**Symptom:** GIFT Nifty (traded ~21 hours/day) appeared to "predict"
NIFTY's next-day open with a strong lagged Granger-causality result — but
the relationship looked suspiciously strong for a genuine overnight signal.

**Diagnosis:** pulled GIFT Nifty's actual intraday bars and found Kite
timestamps them by plain wall-clock IST, midnight to midnight — so a
"daily" GIFT Nifty return silently spans and absorbs NIFTY's own
same-day session return in the middle. The "predictive" signal was mostly
just NIFTY's own move, laundered through a differently-labeled bar.

**Fix:** extracted precise intraday snapshots at the two boundaries that
actually matter — GIFT Nifty's price at 15:30 IST (NIFTY's close) and at
9:15 IST (NIFTY's next open) — and rebuilt the return from exactly that
window. The corrected relationship is real and strong (R²=0.79
contemporaneous) but has **zero forward-looking lead time** once measured
correctly — a genuinely different, more honest conclusion than the buggy
version implied.

## 4. Multiple comparisons: a weekday effect that wasn't

**Symptom:** a momentum-streak effect, split by weekday, showed p=0.036
(Tuesday) and p=0.065 (Thursday) — individually "significant."

**Fix:** ran a permutation test on the *minimum* p-value across all 5
weekday groups tested (`pipeline/validate/stress_tests.py:multiple_comparisons_correction`).
Family-wise corrected p=0.38 — finding the best of 5 random groupings
beating p=0.036 happens by chance alone more than a third of the time.
Retracted.

**Lesson, generalized:** any time a finding is "the best of N subgroups
tested," report the family-wise corrected p-value, not the individual one
— this project applies that check as standard practice in `validate/`, not
as a one-off fix.

## 5. Bias-calibrating a known-biased estimator (Hurst exponent)

The classical R/S Hurst estimator reads ~0.55 even on *pure random-walk
noise* at the window lengths used here — a well-documented small-sample
bias, confirmed by running the identical estimator on 2,000 simulated
random walks. Real NIFTY data was then z-scored against that *simulated
null*, not against the textbook value of 0.5. Result: 95% of days read as
statistically indistinguishable from noise, versus 95% reading as "trending"
under the naive, uncalibrated version — the opposite conclusion.

## 6. Independent re-derivation as final verification

For the one finding the project's headline conclusions leaned on most (a
raw-price momentum streak effect), the entire computation was rewritten
from scratch in a different style — pure-Python loops instead of
numpy/statsmodels, a different RNG seed — specifically to catch a bug that
might have silently persisted across every reuse of the original code. Both
implementations agreed to 3–4 decimal places before the finding was trusted.

## 7. Stress-testing that's allowed to kill things

Every "positive" finding went through the same battery
(`pipeline/validate/stress_tests.py`): temporal-stability split,
outlier-sensitivity check, permutation test against a random same-size
subset. One finding (a backwardation-fade calendar spread) failed outright
— strong in the first half (p=0.006), dead in the second (p=0.73), and lost
significance after removing 3 trades. Another (a VIX-implied-vol-percentile
regime gate) survived the identical battery and *strengthened* under
outlier removal. The discipline only means anything because it was applied
uniformly and allowed to fail things — see `README.md` for the full ledger.
