# Apaleo agent workflow

Skills and runner for taking a Linear issue from a confirmed plan to a draft pull request.

Handbook: https://app.notion.com/p/apaleo/Agentic-AI-Software-Development-Workflow-3ce04b9ee10b80dc9e48f1fe2e0319a1

## Install

Use the folder that already contains `apaleo/` and `development/` on `master`.

```bash
cd /path/to/workspace
git init
git remote add origin git@github.com:marko-arsov/apaleo-agent-workflow.git
git fetch origin
git checkout -f -B master origin/master
./install.sh .
```

Open that folder in Cursor and run `/list-pipeline`.

Product repositories, worktrees, and plans stay untracked. Workflow changes are pull requests in this checkout. After pulling new commands, run `./install.sh .` again.
