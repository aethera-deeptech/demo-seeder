# Security Policy

## Supported versions

Only the latest release and the `main` branch receive security fixes.

## Reporting a vulnerability

Please do not open a public issue for a security problem.

Use GitHub private vulnerability reporting instead. Open the [Security tab](https://github.com/aethera-deeptech/demo-seeder/security) and choose **Report a vulnerability**, or go straight to the [advisory form](https://github.com/aethera-deeptech/demo-seeder/security/advisories/new). The report stays private. Only you, the people who manage security advisories for this repository, and anyone who is added to the report can see it.

A good report includes the following.

- A description of the problem and its impact, for example a way to reach the demo accounts or their data, a way around sign-in or a leaked secret.
- Steps to reproduce it, or a proof of concept.
- The commit or the address of the deployment you tested.
- Relevant logs with any secrets removed.

The report is triaged, fixed in private when it is valid, and, where it makes sense, released with a published advisory. Reporters who want credit are named once the fix has shipped. This project does not promise a reply time.

## Scope

In scope are the code in this repository and its GitHub Actions workflows.

Out of scope are other people's deployments of this project, findings that need a compromised device or server, and reports that only describe missing hardening without a way to exploit it.

Do not run automated scanning or load testing against a live deployment you do not own.
