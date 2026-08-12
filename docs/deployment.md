# Deployment guide

For a new installation, begin with the [quickstart](quickstart.md). Customer mode
must be built before bundle commands are run:

```powershell
python scripts/project/cli.py validate --config config/my-project.yml
python scripts/project/cli.py build --config config/my-project.yml
Set-Location build/<project-name>
```

The remaining commands run from the generated directory. This keeps the upstream
template immutable and makes the rendered namespace and customer adapter reviewable.

Everything is deployed from this repository with a Databricks Asset Bundle. The
workspace UI is used to inspect and demonstrate resources, not to author them.

## Prerequisites

- Databricks CLI 1.3.0 or later authenticated with OAuth (validated with 1.12.1)
- Unity Catalog and Serverless Jobs
- AI/BI dashboards and Genie
- a Serverless or Pro SQL warehouse
- an existing Vector Search endpoint for the optional action-intelligence run

Never store a PAT, workspace credential, confidential workbook, or live result
payload in the repository.

## Local gates

```powershell
python scripts/genie/materialize.py
python scripts/genie/build_space.py
python scripts/quality/validate_repository.py
python scripts/quality/privacy_scan.py
python dashboard/build_dashboard.py

$env:PYTHONUTF8 = "1"
python action_intelligence/playbook_generator/generate_playbook.py `
  --kit-format genie_kit --kit-root . `
  --config config/playbook_blueprint.yml `
  --output-dir action_intelligence/playbook_generator/generated
```

## Core deployment

```powershell
databricks bundle validate --target dev --profile <profile> `
  --var warehouse_id=<warehouse-id>

databricks bundle deploy --target dev --profile <profile> `
  --var warehouse_id=<warehouse-id>

databricks bundle run bootstrap_portfolio --target dev --profile <profile> `
  --var warehouse_id=<warehouse-id>
```

The bundle creates or updates the jobs, dashboard, and Genie space from the files
under `infrastructure/databricks/resources/`.

After deployment, `databricks bundle plan` should report no changes. Existing
Terraform-engine deployments must be migrated once with
`databricks bundle deployment migrate` before native Genie resources can be managed
by the direct engine.

## Genie evaluation

```powershell
python scripts/genie/run_benchmarks.py `
  --profile <profile> `
  --space-id <bundle-genie-space-id> `
  --output reports/output/genie-benchmarks.json
```

The command exits nonzero unless all 12 questions complete with generated SQL and
pass their semantic source gates. Output is ignored because it contains workspace
conversation identifiers and generated SQL.

## Action intelligence

```powershell
databricks bundle deploy --target dev --profile <profile> `
  --var warehouse_id=<warehouse-id> `
  --var vector_search_endpoint=<existing-endpoint> `
  --var llm_endpoint=<serving-endpoint>

databricks bundle run action_intelligence_pipeline --target dev --profile <profile> `
  --var warehouse_id=<warehouse-id> `
  --var vector_search_endpoint=<existing-endpoint> `
  --var llm_endpoint=<serving-endpoint>
```

The first task indexes the generated PDF, the second persists a structured Genie
diagnosis, and the third retrieves playbook guidance and persists the LLM action
plan. Keep the schedule paused until all three tasks pass manually.

## Release gate

Before publishing: verify the SQL acceptance run, 12/12 Genie evaluation, every
dashboard page and filter in the workspace, generated PDF rendering, repository
links, and the privacy scan. Deployment success alone is not visual QA.
