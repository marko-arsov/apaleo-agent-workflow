# Feature argument

Skills that resolve a feature take an issue id, branch, or pull request. `commit`, `push`,
`open-rider`, `pr-oneliner`, and the other scripts that call `resolve_feature_branch` share this rule.

Before running the script:

- The user passed an id, branch, or PR: pass it through. `sl129` and `sl-129` are the same id.
  Do not ask them to add a dash or to confirm a unique match.
- The user passed nothing, and this conversation is about exactly one feature: pass that issue id,
  branch, or PR. One feature means one issue, even when it has several pull requests.
- The user passed nothing, and the current directory is that feature's worktree: pass nothing.
  The script uses the worktree.
- Otherwise ask for the issue id or branch. Do not guess among several features, and do not
  invent one this conversation has not identified.

The script still asks when one id matches several branches.
