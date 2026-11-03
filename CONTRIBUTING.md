# Contributing

Thanks for helping with the demo seeder of the Aethera backend. This guide keeps changes easy to review.

Everyone who takes part in this project follows the [Code of Conduct](CODE_OF_CONDUCT.md).

## Set up

The seeder is written in Python 3.12 or newer and uses only the standard library. It reads a TOML file, and `config/demo.example.toml` lists every setting. The tests start a small fake of the API inside the process, so they need no network and no database. Run them with `python3 -m unittest discover -s . -t .`. The checks in CI also lint with ruff, build the image and scan it, so you only need to run the program when you want to see it work.

## Making a change

1. Branch from `main`. Name the branch `type/short-description`, for example `fix/device-status`, using the same type as your commits.
2. Keep one pull request to one concern. Unrelated changes go into separate branches and pull requests.
3. Write commits in the [Conventional Commits](https://www.conventionalcommits.org/) style, as `type(scope): summary`. The summary is the whole message, so do not add a body. The types are `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore` and `revert`. A pull request cannot be merged while its title or one of its commit messages does not follow this, because the required check "Conventional commits" fails. The check lints every commit message. It only skips the `Merge branch 'main' into <branch>` message that the Update branch button writes, so a `fixup!`, `squash!` or `Revert` message fails. Write a revert as `revert(scope): summary` and squash your fixups before you push. A local merge of `main` fails unless its message reads exactly `Merge branch 'main' into <branch>`, so use the Update branch button or write that message. Fix a message with `git commit --amend` for the last commit, or an interactive rebase for an older one, and force push your own branch.
4. Write code, comments, commit messages and documentation in English. Match the style of the code around your change.
5. Add tests with every behavior change. A bug fix should come with a test that fails without the fix.

Sign your commits with a GPG key, with an SSH key that you added to your GitHub account as a signing key, or with an S/MIME certificate from a trusted authority. The ruleset of `main` does not require a verified signature yet. It will once the release App has made its first verified commit, so sign now and your branch stays ready. The email address of the commit has to be a verified email address of your account for a GPG or S/MIME signature. GitHub explains the setup in [About commit signature verification](https://docs.github.com/en/authentication/managing-commit-signature-verification/about-commit-signature-verification). The squash and rebase buttons are off, because they would replace your signatures, so the commits keep the signatures that they have.

## Checks run in CI

Every check runs in CI on your pull request, so you should not need to run heavy tasks such as full builds or test suites on your own machine. Push your branch, open the pull request and read the results of the checks. Run something locally only when the CI logs cannot explain a failure, and keep it small.

## Names

Names are checked in the pull request, so it is quicker to follow them from the start. Folders are lowercase words joined by hyphens, and a leading dot marks the folder of a tool. Files are lowercase words joined by hyphens, and a dot may mark a variant. Python files are lowercase words joined by underscores, such as `fake_api.py` and `test_seeder.py`. A Markdown file may also be written in capitals joined by underscores, such as `README.md` and `CODE_OF_CONDUCT.md`. YAML files end with `.yml`, except the workflows, which end with `.yaml`. The rules and the few files that are allowed to break them are in [docs/ci-cd.md](docs/ci-cd.md#file-names).

## Pull requests

- The title is a Conventional Commit, such as `fix(devices): keep the status after a restart`. Write the scope in lowercase, with letters, digits, dots, slashes, underscores or hyphens only, because the title check refuses other scopes. The "Conventional commits" check blocks the merge when the title or any commit other than an Update branch merge does not follow it.
- The body is only the list of commits in the pull request, one hyphen bullet per commit. The check accepts lines that start with a hyphen and text, so other bullet marks and indented sub bullets fail. The check does not count the bullets, so keep them in step with the commits yourself.
- Name the branch `type/short-description`, with the type of the commits, such as `fix/device-status`.
- Add one label, `bug` for fixes, `enhancement` for features and `documentation` for documentation only, and assign the pull request to yourself.
- The "PR format" check blocks the merge when the branch name, the label, the assignee or the body does not follow this. Add what is missing and the check runs again by itself. A rerun from the checks tab also reads the pull request as it is now.
- Pull requests are merged with a merge commit, never squashed or rebased.
- Every required check must pass. They are listed in the repository rules and described in [docs/ci-cd.md](docs/ci-cd.md).
- Read the bot comments on your pull request and resolve every review thread.

## Reporting problems

Use the issue templates for bugs and feature requests. Report security problems privately as described in [SECURITY.md](SECURITY.md).
