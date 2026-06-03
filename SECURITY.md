# Security Policy

## Supported versions

WC26 Predict is currently in active test-stage development. Security fixes are applied to the latest `master` branch unless a stable release branch is created.

## Reporting a vulnerability

Please do not disclose security issues publicly before they are reviewed.

For now, open a GitHub issue with minimal reproduction details and avoid posting secrets, tokens, database files, or private API keys.

## Secrets policy

Never commit:

- `.env`
- API keys
- DeepSeek API keys
- API-Football keys
- database backups containing private data
- production credentials
- paid data provider credentials

Use `.env.example` for placeholder configuration.

## Public-output safety

WC26 Predict contains output-safety rules to avoid leaking internal research fields into public reports.

Before publishing generated reports or screenshots, run:

```bash
cd backend
python scripts/audit_public_outputs_no_odds.py
```

## Data policy

Use only data sources you are allowed to use under their own terms. Keep raw provider credentials out of the repository.
