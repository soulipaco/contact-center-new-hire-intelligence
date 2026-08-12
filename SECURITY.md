# Security policy

## Supported versions

Security fixes are applied to the latest tagged release.

## Reporting a vulnerability

Do not open a public issue containing credentials, private workspace identifiers,
customer data, or exploit details. Use GitHub private vulnerability reporting for
the repository. Include affected version, reproduction conditions, and impact.

## Data boundary

This project must never ingest names, emails, telephone numbers, transcripts, or
other direct identifiers. Customer deployments are responsible for pseudonymizing
stable agent identifiers before data reaches the canonical adapter. Secrets belong
in Databricks authentication and secret-management facilities, never YAML files.

