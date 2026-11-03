// The rules for the commit messages of a pull request, checked by .github/workflows/commits.yaml
export default {
  extends: ['@commitlint/config-conventional'],
  // Every message is linted. The default ignores would skip fixup!, squash!, Revert and every merge message, so they are off, and
  // the only message that passes without a type is the merge of the base branch that the Update branch button of GitHub writes
  defaultIgnores: false,
  ignores: [(message) => /^Merge branch 'main' into \S+$/.test(message.trim())],
  rules: {
    // Renovate writes long lines in the body and the footer, and the summary is the whole message of the rest
    'body-max-line-length': [0],
    'footer-max-line-length': [0],
    'footer-leading-blank': [0],
    'header-max-length': [2, 'always', 120],
  },
}
