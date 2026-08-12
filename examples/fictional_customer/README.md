# Fictional customer clean-room example

This example proves that the accelerator can ingest external-shaped Unity Catalog
tables without changes to the governed analytics modules. All values are generated,
fictional, and unrelated to the demo data path.

The fixture uses four intentionally different source tables under
`workspace.cc_fixture_source`; `config.yml` maps them into isolated
`cc_clean_room_*` analytics schemas.

## Create the source tables

```powershell
Set-Location examples/fictional_customer
databricks bundle validate -t dev --profile <profile>
databricks bundle deploy -t dev --profile <profile>
databricks bundle run create_fictional_customer_sources -t dev --profile <profile>
Set-Location ../..
```

## Build and deploy the accelerator

```powershell
python scripts/project/cli.py validate --config examples/fictional_customer/config.yml
python scripts/project/cli.py build `
  --config examples/fictional_customer/config.yml `
  --output build/fictional-customer-clean-room
Set-Location build/fictional-customer-clean-room
databricks bundle validate -t dev --profile <profile> --var warehouse_id=<warehouse-id>
databricks bundle deploy -t dev --profile <profile> --var warehouse_id=<warehouse-id>
databricks bundle run bootstrap_portfolio -t dev --profile <profile> --var warehouse_id=<warehouse-id>
```

Success means the generated adapter, medallion layers, MLflow learning curves,
Prophet forecasts, serving views, and fail-fast acceptance task all complete without
editing a generated notebook.

The maintained release rehearsal also requires `databricks bundle plan` to converge
to zero changes and the generated Genie space to pass all semantic benchmarks. See
the publication-safe aggregates in [validation results](../../docs/validation_results.md).
