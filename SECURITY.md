# Security Policy

## Supported production version

Only the version deployed from the current `main` branch is supported. Store binaries may contain a native shell, but security-sensitive wallet, authentication and transaction logic is maintained server-side.

## Reporting a vulnerability

Do **not** open a public GitHub issue for a suspected vulnerability, leaked credential, customer-data exposure or payment-integrity problem.

Report privately to:

- `app@aplus-solution.de`
- Subject: `SAMS SECURITY REPORT`

Include, where possible:

- affected URL, endpoint or application version
- clear reproduction steps
- expected and observed behavior
- whether personal data, wallet balances or privileged access may be affected
- screenshots or logs with secrets and personal data removed

We will acknowledge a complete report as quickly as operationally possible, preserve relevant audit evidence and classify the incident under the documented incident-response process.

## Security boundaries

The following must never be committed or pasted into issues, pull requests or logs:

- production `.env` files
- SSH private keys
- Apple `.p8` or `.p12` keys and passwords
- Google/Firebase service-account JSON
- Android signing keystores and passwords
- database credentials
- Restic passwords or rclone configuration
- customer exports, database dumps or notification tokens

## Operational response

For a credible incident, the operator should immediately:

1. preserve audit and infrastructure logs;
2. restrict affected accounts or services;
3. rotate exposed credentials;
4. determine affected data and time period;
5. involve management and the appointed privacy/legal contacts;
6. assess GDPR notification duties without delay;
7. restore only from verified backups and document every action.

Detailed procedures are maintained in `docs/INCIDENT-RESPONSE-RUNBOOK-DE.md`.
