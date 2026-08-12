# Action intelligence

This optional operating layer adapts the deployment kit's pipeline and playbook
generator to the contact-center new-hire domain. It goes beyond descriptive BI:

1. `playbook_generator/` builds a reviewed Markdown playbook, retrieval chunks,
   and a presentation-ready PDF from the repo's Genie metadata and domain rules.
2. `notebooks/00_index_playbook.py` writes deterministic chunks to Delta and
   creates or synchronizes a filtered Databricks Vector Search index.
3. `notebooks/01_trends_analysis.py` asks the bundle-managed Genie space for a
   structured readiness diagnosis and persists it to Delta.
4. `notebooks/02_generate_action_plans.py` retrieves the relevant operating
   guidance, invokes a serving endpoint, and persists an evidence-grounded action
   plan to Delta.

The cross-module contract is `question_category=new_hire_readiness`. It is aligned
across `config/pipeline.yml`, the playbook PDF registry, the seeded question, the
retrieval filter, and the expert system prompt.

## Generate the playbook

```powershell
$env:PYTHONUTF8 = "1"
python action_intelligence/playbook_generator/generate_playbook.py `
  --kit-format genie_kit `
  --kit-root . `
  --config config/playbook_blueprint.yml `
  --output-dir action_intelligence/playbook_generator/generated
```

The generated PDF is versioned because it is the reviewed retrieval source. The
chunks and generation summary make changes auditable.

## Deploy

The paused `action_intelligence_pipeline` job is part of the Asset Bundle. Supply
an existing Vector Search endpoint before running it:

```powershell
databricks bundle deploy --target dev --profile <profile> `
  --var warehouse_id=<warehouse-id> `
  --var vector_search_endpoint=<endpoint-name>
```

The LLM endpoint defaults to `databricks-meta-llama-3-3-70b-instruct` and can be
overridden with `--var llm_endpoint=<endpoint-name>`. The schedule remains paused
until the endpoint, generated PDF, and first manual run have been verified.
