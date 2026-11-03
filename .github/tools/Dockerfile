# The update bot reads this file for the images that the workflows run with docker run, because it does not read run steps.
# Nothing builds it. The workflows read the image of a stage from this file, so a bump here is the bump the jobs use.
FROM rhysd/actionlint:1.7.12@sha256:b1934ee5f1c509618f2508e6eb47ee0d3520686341fec936f3b79331f9315667 AS actionlint
FROM dotenvlinter/dotenv-linter:4.0.0@sha256:49a3c89203aeabb814e7fc028c4bcaf569c6ead29e58dbad5e348324d042d120 AS dotenv-linter
FROM ghcr.io/zizmorcore/zizmor:1.30.1@sha256:a2eb396d886c053073405c7a980f2139ba2248ec172243cfa3841e57196e8101 AS zizmor
FROM hadolint/hadolint:v2.15.1@sha256:32dac94127fd60b7b7e3fbfc65e1383b9b5e25c9bfd7b8536de7a539fe68a12d AS hadolint
FROM zricethezav/gitleaks:v8.30.1@sha256:c00b6bd0aeb3071cbcb79009cb16a60dd9e0a7c60e2be9ab65d25e6bc8abbb7f AS gitleaks
FROM ghcr.io/astral-sh/ruff:0.17.2@sha256:d69a8c8d529a866a6aaea0dfda672693d68671a08827db765514abc1571a78a0 AS ruff
FROM koalaman/shellcheck:v0.11.0@sha256:61862eba1fcf09a484ebcc6feea46f1782532571a34ed51fedf90dd25f925a8d AS shellcheck
