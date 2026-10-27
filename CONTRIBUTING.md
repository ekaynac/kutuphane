# Contributing

## Changes

- Work on a branch and open a pull request against `main`. Do not push to `main`.
- Use conventional commits: `type(scope): description` (`feat`, `fix`, `docs`, `refactor`, `test`, `chore`, …).
- Write a regression test for each behavior that a user can see, then the code.
- Keep it simple (D53): each field must change a behavior.
- Run the tests before you ask for a review:

  ```sh
  .venv/bin/python -m pytest -q
  (cd kstd/reference && ../../.venv/bin/python -m pytest -q -p no:cacheprovider)
  ```

  The first command needs `KUTUPHANE_TEST_DSN` (see `docs/guide/install.md`).

## Documentation

Rule D75: the documentation changes in the same PR as the feature.

- Update the pages of `docs/guide/` that the change affects: commands, flags, tools, routes, settings, errors.
- Add one entry to `docs/guide/changelog.md` under the merge date: what a user or operator sees, with the PR link.
- Update `README.md` when the quick start, the MCP tool list, the security summary or the status changes.
- Document only what exists in the code. Check each command with `--help` and each tool with `tools/list`.
- Write prose in ASD-STE100 Simplified Technical English. Code blocks are exact.
