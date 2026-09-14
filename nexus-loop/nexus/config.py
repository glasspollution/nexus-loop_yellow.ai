"""Detection parameters (handoff section 14.2).

Set on the practice corpus, the benchmark dev split and generator corpora; never tuned on the benchmark
test split. Changing any value changes what is detected: re-run validation/run_all.py after every change.
"""

CFG = dict(
    Z=4.0,              # bad-direction statistic required after overdispersion (and sibling spread)
    MATERIAL_REL=0.10,  # minimum relative effect
    MATERIAL_ABS=0.01,  # minimum absolute effect for rates
    MIN_RUN=3,          # firing windows AND supporting days an episode needs
    CUR=3,              # current-window length; overridden per scale in multiscale.py
    BASE=15,            # self-baseline length in days
    BASE_MIN_DAYS=3,    # minimum days with data in a baseline
    MIN_N_CUR=30,       # units in the current window
    MIN_N_BASE=60,      # units in the baseline
    DAY_MIN_N=5,        # units for a single day to count as support
    NEWBORN_DAY=2,      # a cohort first seen on/after this day is compared with its siblings
    PHI_WINDOW=7,       # half-width of the neighbourhood used to estimate overdispersion
    SUPPORT_FRAC=0.5,   # a supporting day carries at least half of the strongest change
)

SCALES = (3, 7)         # current-window lengths; a 7-day episode needs 7 supporting days

# Stage-3 thresholds are read with defaults inside incidents.py (c.get(name, default)); pass them in CFG
# to override: GLOBAL_BREADTH 0.6, metric-unit equivalence 0.8, window tolerance 3 days,
# volume spike > median + 6*MAD and > 1.5x median, share shift >= 5 points and z >= 4.
