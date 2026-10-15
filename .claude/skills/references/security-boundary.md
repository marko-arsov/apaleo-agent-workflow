# Local pipeline security boundary

This workflow runs on a developer host. Deterministic hooks and sanitisation reduce mistakes; they
do not create an OS or network sandbox.

| Primary control | Current state | Consequence |
|---|---|---|
| Token scope/lifetime | Provider, GitHub, Jenkins, package, and Docker credentials are inherited from host configuration. The runner cannot prove per-stage scope or short lifetime. | A compromised stage may have more identity than it needs. |
| Tool allowlisting | Manifest paths, immutable plans, worktree checks, and hooks constrain outcomes, but provider CLIs use broad/yolo permission flags. | Prompt policy is not a filesystem boundary. |
| Network egress | No stage-specific outbound firewall is installed. Provider, git, package, Docker, and GitHub traffic share host egress. | An untrusted input can coexist with an exfiltration route. |
| Three-way coexistence | AI stages may simultaneously see untrusted data, host write-capable credentials, and outbound network. | Sanitisation is secondary defence, not containment. |

Known external text is stripped of hiding/control characters and HTML comments, delimited as data,
and flagged for confirmation when it resembles injected steering. Secret/convention scanning runs
on the diff. These controls reduce likelihood and catch some outcomes; they do not eliminate the
primary boundary gaps above.

Safer host credential issuance, OS isolation, and egress allowlisting require platform/organization
changes or a new execution profile. They are intentionally reported rather than silently added to
this workflow. Repository CI SAST/dependency/architecture gates are likewise deferred because this
workflow-only change cannot modify application repositories.
