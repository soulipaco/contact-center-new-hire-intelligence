# Lakehouse and ML pipeline

`notebooks/` is the executable data product in dependency order:

1. deterministic synthetic Bronze generation
2. typed Silver dimensions/fact and enriched Gold outputs
3. four-family learning-curve comparison with MLflow and UC registration
4. six-month Prophet forecasting
5. eight serving views for semantic and presentation consumers
6. fail-fast data/model/serving acceptance checks

The same files are referenced directly by the bundle jobs. There is no separately
maintained workspace copy.
