## MR !2

Risk gate verdict for this release: **MEDIUM**

### Features
- **billing:** loyalty discount

### Tests
- **riskgate:** pin loyalty cap and tax arithmetic
- **riskgate:** cover loyalty_discount, legacy_total

### Rollback plan
1. In **Deploy > Releases**, note the release before `MR !2`.
2. Re-run the `pages` job (production gate) from that tag's pipeline, or revert the merge commit and let the pipeline redeploy.
3. Confirm the `post_deploy_probe` job is green.

