# Test strength: targeted mutation check

Passing tests prove little if a plausible wrong implementation would also pass them. This check
breaks the product code on purpose, the way a careful reviewer does, and confirms that a test
notices. Review runs it in the pipeline. `/implement` runs it during its manual-lane self-review.

## When

After the tests are green, on the final product code (after Tier 1 fixes in review).

## Pick the mutants

Choose 3–5. For each acceptance criterion, find the line or two in the diff that make it true, and
change them into the most plausible wrong version:

- the old or fallback source of a value (for example `GrossDailyRate` instead of the stored
  per-night `GrossRate`);
- the alternative the plan rejected in a `D#`;
- the new branch or condition removed;
- the feature-flag, permission, or property-scope check skipped;
- two similar fields swapped, or an inclusive range made exclusive.

Prefer the mutants that a test with equal or default values would miss.

## Run each one

1. Copy the file before you edit it. Apply one mutant.
2. Run the narrowest test that covers it: a filtered unit or integration test. Use E2E only when no
   lower-level test covers the behaviour, and then for at most two mutants per run. Each E2E
   mutant needs the stack lock and a branch-image rebuild (`references/e2e-stack.md`), and the
   prior image is restored afterwards.
3. **Killed**: a test failed because of the mutant. Restore the file.
4. **Survived**: the tests are too weak. Restore the file, then add a hardening test or case in a
   `test_paths` file whose data separates the correct code from the mutant (distinct prices,
   dates, ids). Never edit an existing assertion. Re-apply the mutant once to confirm the new test
   kills it, then restore the file again.
5. Before the next mutant, `git diff -- <file>` must show no mutant lines.

A mutant that cannot be built or run is recorded as not checked, never as killed.

## Record

```markdown
## Test strength
| Mutant | Where | Result |
|---|---|---|
| Fallback rate instead of stored night rate | `apaleo/src/.../BlockDto.cs:90` | killed by `PicksStoredNightRate` |
| Flag check skipped | `apaleo/src/.../Converter.cs:95` | survived → added `UsesFlatRateWhenFlagOff` |
```

Review writes this table in `review-<n>.md`; `/implement` writes it in `progress.md`.
