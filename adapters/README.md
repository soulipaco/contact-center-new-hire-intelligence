# Source adapters

Adapters are the only customer-specific part of the data path. They map existing
Unity Catalog tables into the four canonical Bronze contracts under `contracts/`.
The Silver, Gold, ML, dashboard, Genie, and action-intelligence modules must not be
edited to accommodate source-system column names.

Generate an adapter from a customer configuration:

```powershell
python scripts/project/cli.py render-adapter --config config/my-project.yml
```

The generated, reviewable SQL notebook is written to
`lakehouse/generated/00_customer_adapter.sql`. It deliberately contains no
credentials or copied source data.

