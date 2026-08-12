# Configuration reference

`config/project.yml` is the checked-in demo configuration.
`config/project.customer.example.yml` is the customer-mode template.

## Project

- `project.name`: filesystem-safe build name.
- `project.mode`: `demo` or `customer`.
- `project.catalog`: target Unity Catalog catalog.
- `project.schemas`: Bronze, Silver, Gold, and registered-model schema names.

The build command renders every governed table reference into a separate ignored
directory under `build/`; it never rewrites the source template.

## Analytics

- `new_hire_days`: inclusive new-hire classification boundary.
- `tenured_baseline_min_days`: first day eligible for tenured comparison.
- `learning_curve_max_days`: observation horizon used for model fitting.
- `forecast_periods`: number of future monthly periods.
- `forecast_interval_width`: Prophet uncertainty interval.
- `outliers.z_score_threshold`: absolute parametric outlier threshold.
- `outliers.iqr_multiplier`: Tukey-fence multiplier.

The builder renders these values into the relevant notebooks. Milestone columns at
days 30, 60, and 90 remain part of the current public semantic contract.

## Features

`dashboard`, `genie`, and `action_intelligence` control which optional bundle
resource files appear in the generated repository. Action Intelligence requires
both Genie and Vector Search. Learning-curve ML and forecasting are core analytical
dependencies in the current release and cannot yet be disabled.

## Source

Demo mode accepts `source.synthetic_seed`. Customer mode requires four three-level
Unity Catalog table names and canonical-to-source column mappings. Mapping values
must be simple column names; arbitrary SQL expressions are intentionally rejected.
Create upstream views when transformations are required.
