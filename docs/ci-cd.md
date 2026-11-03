# CI/CD

This page lists every workflow of the repository, what it checks and which checks block a merge. The workflows follow the same pattern as the Aethera backend, so the two repositories behave alike.

## Workflows

| Workflow | File | Runs on | What it does |
|:---|:---|:---|:---|
| CI | `ci.yaml` | push to main, pull request | Runs the unit tests with coverage, checks the example configuration and uploads the coverage to Codecov |
| Config lint | `config.yaml` | push to main, pull request | Lints the workflows, the Dockerfile, the shell scripts, the env example, the compose file, the Python code, the file names and the Renovate configuration |
| Security | `security.yaml` | push to main, pull request, schedule | Runs CodeQL, dependency review, gitleaks, Trivy on the file system and OSSF Scorecard |
| Docker | `docker.yaml` | push to main, tag, pull request | Builds the image for amd64 and arm64, scans it, pushes it to GHCR, then signs it and attaches the SBOM |
| Docker Hub mirror | `docker-hub-mirror.yaml` | after Docker | Verifies the signature of the GHCR image and copies it to Docker Hub as `aethera-demo-seeder` under the account in `DOCKERHUB_USERNAME` |
| Re-sign | `resign.yaml` | manual | Signs an image again when a signature is missing |
| Conventional commits | `commits.yaml` | pull request | Checks every commit message and the pull request title with commitlint |
| PR format | `prformat.yaml` | pull request | Checks the branch name, the label, the assignee and the body |
| Release Please | `release-please.yaml` | push to main | Opens and updates the release pull request, and makes the tag and the release when it is merged |
| Vale | `vale.yaml` | push to main, pull request, manual | Lints the Markdown files with Vale |
| Links | `links.yaml` | schedule, manual | Checks the links of the Markdown files |

## Required checks

The ruleset of the default branch is applied after the repository is public and every check has reported once on a pull request. Each required check is pinned to GitHub Actions as its source.

- Conventional commits
- PR format
- Tests
- Actionlint, Zizmor, Hadolint, ShellCheck, Dotenv lint, Compose config, Python lint, File names and Renovate config
- Dependency review, Secret scan (gitleaks) and CodeQL
- Build, scan and push image

Codecov, CodeRabbit, Trivy and OSSF Scorecard are not required, because they can report late or on a schedule only.

## Container image

The image has one stage on `python:3.14-alpine` and runs as user 10001. The Docker workflow pushes it to GHCR with the tags `latest` and `sha-<short>` from main, and with the version tags from a release tag. Cosign signs it without a key, and the SBOM is attached as an attestation. The Docker Hub mirror verifies that signature before it copies anything, so only an image that main built is published. The deploy pulls `syafa/aethera-demo-seeder:<version>` from Docker Hub.

## Pulling images

Every job that pulls an image from Docker Hub goes through `.github/actions/pull-images`. The action logs in with the read-only token `DOCKERHUB_PULL_TOKEN`, tries the Google mirror first and falls back to Docker Hub when the mirror has no copy.

## Pinned tools

The tools that run in a container are pinned by digest in `.github/tools/Dockerfile`, and every action is pinned to a full commit SHA with a version comment. Renovate raises the updates once a week.

## File names

The names of the files follow `.ls-lint.yml`. Folders and files use lowercase words joined by hyphens, Python files use underscores, the community files are in capitals and workflows end with `.yaml`.

## Releases

Release Please reads the Conventional Commits on main and keeps one release pull request open. Merging it creates the tag and the release. The release GitHub App creates the tag, so the tag ruleset allows nobody else to make a `v*` tag. The version in `seeder/__init__.py` is updated by the same pull request.

## Secrets and variables

| Name | Kind | Used by |
|:---|:---|:---|
| `DOCKERHUB_USERNAME` | variable | image pulls and the mirror |
| `DOCKERHUB_PULL_TOKEN` | repository secret | read-only pulls from Docker Hub |
| `DOCKERHUB_TOKEN` | secret of the `docker-hub` environment | the push to Docker Hub |
| `CODECOV_TOKEN` | repository secret | the coverage upload |
| `RELEASE_APP_CLIENT_ID` | variable | Release Please |
| `RELEASE_APP_PRIVATE_KEY` | secret of the `release` environment | Release Please |
