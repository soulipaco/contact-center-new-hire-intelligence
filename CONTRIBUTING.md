# Contributing

Thank you for helping improve the Contact Center New-Hire Intelligence accelerator.

1. Open an issue for significant contract, metric, or architecture changes.
2. Create a focused branch and do not include customer data, workspace credentials,
   generated build directories, or personally identifiable information.
3. Add or update tests and documentation with every behavioral change.
4. Run the local release gates:

```powershell
python scripts/project/cli.py validate
python scripts/genie/materialize.py
python scripts/genie/build_space.py
python dashboard/build_dashboard.py
python scripts/quality/validate_repository.py
python scripts/quality/privacy_scan.py
python -m pytest -q
```

Pull requests that change KPI semantics must state the grain, numerator,
denominator, direction, target behavior, and expected dashboard impact.

