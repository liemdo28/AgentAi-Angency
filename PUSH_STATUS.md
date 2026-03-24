# Push Status

## Attempted command
- `git push`

## Result
- Failed because this local repository has no configured remote push destination.
- Error from git:
  - `fatal: No configured push destination.`

## What is needed to complete push
1. Add remote:
   - `git remote add origin <github_repo_url>`
2. Push branch:
   - `git push -u origin work`

## Current branch
- `work`
