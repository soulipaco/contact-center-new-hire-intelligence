# Troubleshooting

## Configuration validation fails

Run `python scripts/project/cli.py validate --config <file>`. Every message names the
invalid setting or missing mapping. Source tables must use three-level Unity Catalog
names and mappings must contain simple column names.

## The build directory already exists

Builds are intentionally immutable. Choose another `--output` path or remove the
old ignored build directory after confirming it contains no work you need.

## Bronze rows disappear in Silver

Check that agent and target effective-date ranges cover every performance date,
denominators are positive, agent/cohort IDs reconcile, and performance dates occur
on or after `first_day_in_production`.

## No tenured baseline or control limits

Supply observations at or beyond `tenured_baseline_min_days`. Sigma calculations
also need enough distinct agents for a non-null sample standard deviation.

## Weak or missing learning curves

Confirm that cohorts contain observations across the configured learning horizon.
R-squared measures fit quality; it does not establish causality.

## Bundle reports remote dashboard drift

Do not automatically use `--force`. Export or inspect the remote dashboard first,
reconcile intentional changes into `dashboard/build_dashboard.py`, regenerate the
artifact, and then rebind or redeploy through the supported Databricks workflow.

## Genie requires the direct deployment engine

Use Databricks CLI 1.3.0 or later and keep `bundle.engine: direct`. If this target
was previously deployed with Terraform, run `databricks bundle deployment migrate`
once and then deploy again. Confirm convergence with `databricks bundle plan`.

Databricks CLI 0.280.0 also shipped with an expired Terraform provider signing key;
upgrade instead of weakening signature verification.

## Action Intelligence is absent

Set `action_intelligence` and `vector_search` to true, configure both endpoints,
regenerate the deployable build, and run the optional action workflow manually
before enabling a schedule.
