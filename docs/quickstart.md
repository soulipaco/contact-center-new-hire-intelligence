# Quickstart

The accelerator supports two paths. **Demo mode** creates deterministic fictional
data. **Customer mode** maps four of your Unity Catalog tables into the canonical
contracts without copying source-system names into the analytics layer.

## Prerequisites

- Python 3.11 or later
- Databricks CLI 1.3.0 or later with an authenticated profile (native bundle-managed Genie requires the direct engine)
- A Unity Catalog-enabled Databricks workspace
- A SQL warehouse for the dashboard and Genie
- Permission to create schemas, tables, models, jobs, and dashboard resources

Vector Search and a model-serving endpoint are required only when Action
Intelligence is enabled.

## Try the fictional demo

```powershell
python -m pip install -r requirements.txt
python scripts/project/cli.py validate
python scripts/project/cli.py build --config config/project.yml
cd build/contact-center-new-hire-intelligence
python scripts/quality/validate_repository.py
databricks bundle validate -t dev --profile <profile> --var warehouse_id=<warehouse-id>
databricks bundle deploy -t dev --profile <profile> --var warehouse_id=<warehouse-id>
databricks bundle run bootstrap_portfolio -t dev --profile <profile> --var warehouse_id=<warehouse-id>
```

## Connect your own data

Create a customer configuration:

```powershell
python scripts/project/cli.py init --output config/my-project.yml
```

Edit the four table names and their column mappings. Then run:

```powershell
python scripts/project/cli.py validate --config config/my-project.yml
python scripts/project/cli.py build --config config/my-project.yml
cd build/<your-project-name>
python scripts/quality/validate_repository.py
databricks bundle validate -t dev --profile <profile> --var warehouse_id=<warehouse-id>
databricks bundle deploy -t dev --profile <profile> --var warehouse_id=<warehouse-id>
databricks bundle run bootstrap_portfolio -t dev --profile <profile> --var warehouse_id=<warehouse-id>
```

The generated repository contains a reviewable
`lakehouse/generated/00_customer_adapter.sql`. The downstream Silver, Gold, ML,
dashboard, and Genie logic remains unchanged.

For a completely independent, fictional source-system rehearsal, follow the
[clean-room example](../examples/fictional_customer/README.md).

## Before running customer data

Read [data contracts](data_contracts.md) and run the generated adapter first in a
development catalog. Confirm that identifiers are pseudonymous and that the four
Bronze tables contain no confidential free-text fields.
