# Azure architecture (cross-project reference)

The five banking-policy projects share one Azure subscription
(`Azure subscription 1`, `70e0cd03-fbee-44bb-8617-4b2ea3f12837`). This doc is the
single map of what's deployed, what's cruft, and the target layout. It lives in
`banking-commons` because the shared resource (ACS email) is the infra twin of
the shared `banking_commons.email` code.

> Snapshot date: 2026-06-13, **after P1 cleanup**. Re-run the audit commands at
> the bottom if it's been a while.

## Current state

| Project | Compute | Data storage → contents | Email | Resource group(s) |
| --- | --- | --- | --- | --- |
| ai_news_feed | Functions **Flex** (`feltonainews`) | `feltonainews` → `ProcessedPapers` | ACS `ainewsfeed` (mgd-identity storage) | **feltonainews** (compute) + **ai_news_feed** (ACS only) |
| banking-legislation-tracker | Functions **Consumption** (`EastUSLinuxDynamicPlan`) | `bankinglegislation` → `TrackedBills`, `TrackerMeta` | ACS `ainewsfeed` (conn-string) | bank-data |
| bank-filings-pipeline | local cron | `bankdata1` → `FilingsManifest`, `sec-filings` | ACS `ainewsfeed` | bank-data (storage only) |
| comment_summarization | local launchd | local FS | ACS `ainewsfeed` | — (local only) |
| congressional-transcripts | local | local FS | — | — |

**All four email senders share one ACS resource** (`ainewsfeed`). That sharing is
correct; the remaining issue is it's named after one app and lives alone in the
`ai_news_feed` RG. P2 relocates it to a neutral shared RG.

### Removed in P1 — ✅ done 2026-06-13

| Resource | Group | Status |
| --- | --- | --- |
| `ainewsfeedstorage` (storage) | ai_news_feed | deleted |
| `ainewsfeed` (storage) | ai_news_feed | deleted |
| `ainewsfeed` (App Insights) | ai_news_feed | deleted |
| `ainewsfeed-uami` (managed identity) | ai_news_feed | deleted |
| `regulations1` (storage) + `regulations` RG | regulations | deleted (RG gone) |

After P1 the `ai_news_feed` RG holds only the live ACS, plus one harmless
leftover — an auto-created `Application Insights Smart Detection` action group
(orphaned when its App Insights was deleted). It costs nothing and disappears
when the RG is removed at the end of P2; delete early if you want it gone:
`az resource delete --ids "$(az resource show -g ai_news_feed -n 'Application Insights Smart Detection' --resource-type microsoft.insights/actiongroups --query id -o tsv)"`

> ⚠️ **Same-name note (still relevant for P2):** `ainewsfeed` is the name of the
> live ACS (Microsoft.Communication). The identically-named storage account is
> now gone, but keep checking resource *type* when you operate on `ainewsfeed`.

### What's inconsistent

- **Two Function apps, two of everything:** Flex vs Consumption hosting;
  **managed identity** (ai_news_feed) vs **connection strings** everywhere
  (banking-legislation-tracker); separate App Insights; no shared workspace.
- **RG taxonomy:** one app split across two RGs (`ai_news_feed` + `feltonainews`);
  one RG holding two projects (`bank-data`); a legacy-only RG (`regulations`);
  three naming styles.
- **Email env-var names split:** `ACS_*` (comment_summarization,
  banking-legislation-tracker) vs `AZURE_COMMUNICATION_*` / `EMAIL_*`
  (ai_news_feed, bank-filings). `banking_commons.email` accepts both today.

## Target state

```
rg-banking-shared          acs-banking (+ managed domain)   ← all 4 senders
rg-ainewsfeed              Func ai_news_feed (Flex, MI) + data storage + insights
rg-banking-legislation     Func banking-legislation (Flex, MI) + data storage + insights
rg-bank-filings            bankdata1 (FilingsManifest, sec-filings)
(comment_summarization, congressional-transcripts stay local — no RG)
```

Principles: one project per RG; `rg-<project>` kebab naming; **Flex Consumption +
managed identity** for both Function apps; one shared ACS in a neutral RG;
shared telemetry workspace; standardize on the `ACS_*` env-var names (the alias
list in `banking_commons.email` can then be retired).

## Migration phases

- **P1 — cleanup ✅ done (2026-06-13):** deleted the 5 cruft resources and the
  empty `regulations` RG. Removed 3 storage accounts, a duplicate App Insights,
  an orphan identity, and a whole RG, with no impact on anything live.
- **P2 — shared ACS (next):** stand up `rg-banking-shared` + `acs-banking`,
  repoint all four senders, retire the old ACS, then delete the now-ACS-only
  `ai_news_feed` RG. (ACS + managed domain can't be moved in place; recreate and
  re-verify the sender domain. Note: a new Azure-managed domain means a new
  sender address — update `ACS_SENDER_ADDRESS` / `EMAIL_SENDER` in all four
  senders, or bring your own domain to keep the address stable.)
- **P3 — standardize Functions:** move banking-legislation-tracker to Flex +
  managed identity (drop connection strings), align Python 3.12, shared workspace.
- **P4 — RG taxonomy:** split `bank-data`, rename to the `rg-<project>` scheme.

---

## P1 cleanup runbook

> ✅ **Executed 2026-06-13.** Kept for reference / reproducibility. Verified
> afterward: the `regulations` RG is gone and the `ai_news_feed` RG holds only
> the ACS (+ the leftover action group noted above).

Read-only verification first; destructive commands are clearly marked.

```bash
SUB=70e0cd03-fbee-44bb-8617-4b2ea3f12837
az account set --subscription "$SUB"

# --- VERIFY (read-only) -------------------------------------------------------
# 1. ai_news_feed RG has no compute (cruft is data-plane only):
az resource list -g ai_news_feed --query "[?contains(type,'Microsoft.Web')]" -o tsv   # expect empty

# 2. Live app writes to feltonainews storage, not the stale ainewsfeed one:
az functionapp config appsettings list -g feltonainews -n feltonainews \
  --query "[?name=='AzureWebJobsStorage__tableServiceUri'].value" -o tsv             # expect feltonainews.table...

# 3. Live app's identity is feltonainews-identities-*, not ainewsfeed-uami:
az functionapp identity show -g feltonainews -n feltonainews -o json                 # check userAssignedIdentities

# 4. ainewsfeedstorage holds no data tables (only app-package/webjobs):
az storage table list --account-name ainewsfeedstorage --auth-mode login -o tsv      # expect empty

# --- BACKUP data before deleting (optional but recommended) -------------------
az storage entity query --account-name ainewsfeed --table-name ProcessedPapers \
  --auth-mode login -o json > ~/backup_ainewsfeed_ProcessedPapers.json
for t in Arguments Clusters comments ConsolidatedPositions Letters proposals ScrapingMetadata; do
  az storage entity query --account-name regulations1 --table-name "$t" \
    --auth-mode login -o json > "$HOME/backup_regulations1_$t.json"
done

# --- DELETE (destructive) -----------------------------------------------------
# Dead old-deployment storage (note: STORAGE accounts, NOT the ACS of same name):
az storage account delete -n ainewsfeedstorage -g ai_news_feed --yes
az storage account delete -n ainewsfeed        -g ai_news_feed --yes

# Duplicate App Insights + orphan managed identity:
az resource delete --ids "$(az resource show -g ai_news_feed -n ainewsfeed \
  --resource-type microsoft.insights/components --query id -o tsv)"
az identity delete -n ainewsfeed-uami -g ai_news_feed

# Abandoned v1 backend of comment_summarization, then drop its now-empty RG:
az storage account delete -n regulations1 -g regulations --yes
az group delete -n regulations --yes

# --- LEFT INTACT --------------------------------------------------------------
# ACS  'ainewsfeed' (Microsoft.Communication/*) — still the shared email sender.
# Move/rename it in P2, not here.
```

After P1, `ai_news_feed` RG holds only the live ACS (`ainewsfeed`). P2 relocates
it to `rg-banking-shared`, after which the `ai_news_feed` RG can also be deleted.

## Audit commands (rebuild this map)

```bash
az group list -o table
az resource list --query "sort_by([].{group:resourceGroup,type:type,name:name},&group)" -o table
# per storage account: data-plane contents
az storage table list     --account-name <acct> --auth-mode login -o tsv
az storage container list --account-name <acct> --auth-mode login -o tsv
```
