# AI/BI dashboard module

`build_dashboard.py` generates the version-controlled Lakeview artifact from 16
governed views. The dashboard contains nine pages and 74 widgets covering executive
readiness, persisted AI recommendations, observed and fitted learning curves, volume
progression, tenure and volume regression, Lean Six Sigma process control, z-score
and IQR outliers, cohort comparison, forecast uncertainty, and pseudonymous agent
drill-through.

The bundle deploys `contact_center_new_hire_ramp.lvdash.json`; `deploy_dashboard.py`
is retained only as an API fallback. Visual interaction QA must be performed on the
published bundle resource after every material widget or view change.
