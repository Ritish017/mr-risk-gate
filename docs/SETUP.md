# Setup on GitLab.com (human steps)

All steps are free. No card is required by the hackathon; GitLab may ask for SMS identity verification.

## 1. Accounts and access (do first — approval takes ~24 business hours)
1. GitLab.com account (sign up with kurmaritish017@gmail.com or Google). Verify email.
2. Devpost: join https://gitlab-transcend.devpost.com/ (Join hackathon).
3. Start contributor onboarding: https://contributors.gitlab.com/transcend-hackathon
   → sign in with GitLab → request access. Wait for approval (≈24 business hours).
4. After approval you get a group + subgroup with the **Developer + AI** role, a project and an
   onboarding issue (path like `gitlab.com/gitlab-ai-hackathon/transcend-october-2026/<id>/...`).
5. If GitLab shows an identity-verification banner on **AI > Flows/Agents** or when CI runs, complete
   it at https://gitlab.com/-/identity_verification (SMS to +91 is normally enough; a card is only
   asked of accounts GitLab scores high-risk — stop and reassess if that happens).
6. Check credits: https://gitlab.com/-/profile/gitlab_credits_dashboard (500/month for participants).

## 2. Put the code in the provisioned project
```bash
git clone <provisioned-project-url> riskgate && cd riskgate
cp -r /path/to/builds/gitlab/app/. .
git add -A && git commit -m "feat: MR Risk Gate initial import" && git push origin main
```
Make the project **Public** (Settings > General > Visibility) and confirm the MIT license shows in the
About panel. If you lack permission to change visibility, ask in Discord #transcend-hackathon.

## 3. CI/CD
- Push triggers the first pipeline. If jobs never start (forum report: "pipelines fail instantly with
  zero jobs"), register a free project runner on your own machine:
  Settings > CI/CD > Runners > New project runner (tag none, run untagged) → follow the
  `gitlab-runner register` command shown, executor `docker`. Ask organisers to confirm this is fine.
- On `main`, run the manual **pages** job once (this is the production approval). The Pages URL
  appears under Deploy > Pages; `post_deploy_probe` then checks `/health.json`.
- Optional: tag `v0.1.0` to exercise `publish_package` + `create_release`.

## 4. Duo flows and agent
1. Project > **AI > Flows > New flow** → name "MR Risk Gate", visibility Public, paste
   `.gitlab/duo/flows/mr-risk-gate.yaml` → Create.
2. Open it → **Enable** in this project → triggers: **Merge request → Created** and **Assign reviewer**.
3. Repeat for "Pipeline Medic" (`pipeline-medic.yaml`) → trigger **Pipeline events → Failed**.
4. Project > **AI > Agents > New agent** → "Release Captain" from `.gitlab/duo/agents/release-captain.yaml`
   (system prompt + the listed tools) → Enable.
5. Note the service-account usernames (`ai-<flow>-<group>`); you can also start the flow by assigning
   it as reviewer or mentioning it on an MR.

## 5. Demo run (record this)
1. Branch `feat/loyalty-discount`: add the `loyalty_discount` + `legacy_total` functions from
   `scripts/demo_local.sh` to `tinyledger/billing.py`; open an MR → watch triage note (MEDIUM),
   test-author commit, new pipeline, release-scribe summary.
2. Branch `docs/readme`: README-only MR → triage LOW → straight to summary (no test agent).
3. Break a test on an MR branch → pipeline fails → Pipeline Medic note/fix.
4. Ask Release Captain in Duo Chat: "Is !1 safe to ship?"
5. Merge → run manual `pages` → probe green → open the ledger site.
Keep the session links (Automate > Agent sessions) for the submission text.
