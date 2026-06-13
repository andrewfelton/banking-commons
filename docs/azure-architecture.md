# Azure architecture (cross-project reference)

The five banking-policy projects share one Azure subscription
(`Azure subscription 1`, `70e0cd03-fbee-44bb-8617-4b2ea3f12837`). This doc is the
single map of what's deployed, what's cruft, and the target layout. It lives in
`banking-commons` because the shared resource (ACS email) is the infra twin of
the shared `banking_commons.email` code.

> Snapshot date: 2026-06-13. Re-run the audit commands at the bottom if it's
> been a while.

## Current state

| Project | Compute | Data storage → contents | Email | Resource group(s) |
| --- | --- | --- | --- | --- |
| ai_news_feed | Functions **Flex** (`feltonainews`) | `feltonainews` → `ProcessedPapers` | ACS `ainewsfeed` (mgd-identity storage) | **feltonainews** (compute) + **ai_news_feed** (email + dead storage) |
| banking-legislation-tracker | Functions **Consumption** (`EastUSLinuxDynamicPlan`) | `bankinglegislation` → `TrackedBills`, `TrackerMeta` | ACS `ainewsfeed` (conn-string) | bank-data |
| bank-filings-pipeline | local cron | `bankdata1` → `FilingsManifest`, `sec-filings` | ACS `ainewsfeed` | bank-data (storage only) |
| comment_summarization | local launchd | local FS (+ abandoned `regulations1`) | ACS `ainewsfeed` | regulations (legacy only) |
| congressional-transcripts | local | local FS | — | — |

**All four email senders already share one ACS resource** (`ainewsfeed`). That
sharing is correct; the problem is it's named after one app and stranded in a
half-abandoned resource group.

### Cruft (verified unreferenced — see audit commands)

| Resource | Group | Why it's dead |
| --- | --- | --- |
| `ainewsfeedstorage` (storage) | ai_news_feed | only holds an old app-package; no data tables |
| `ainewsfeed` (storage) | ai_news_feed | `ProcessedPapers` here is stale — the live app writes to `feltonainews`'s copy |
| `ainewsfeed` (App Insights) | ai_news_feed | duplicate; live app reports to `feltonainews` insights |
| `ainewsfeed-uami` (managed identity) | ai_news_feed | old; live app uses `feltonainews-identities-*` |
| `regulations1` (storage) | regulations | v1 cloud backend of comment_summarization; current app is local-FS only |

> ⚠️ **Same-name trap:** `ainewsfeed` is BOTH a storage account and the live ACS
> (Microsoft.Communication). Deleting the **storage account** does not touch the
> ACS — different resource types — but double-check the resource type on every
> delete.

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

- **P1 — cleanup** (runbook below): delete the 5 cruft resources, drop the empty
  `regulations` RG. Removes ~3 storage accounts, a duplicate App Insights, an
  orphan identity, and a whole RG. Non-destructive to anything live.
- **P2 — shared ACS:** stand up `rg-banking-shared` + `acs-banking`, repoint all
  four senders, retire the old ACS. (ACS + managed domain can't be moved in
  place; recreate and re-verify the sender domain.)
- **P3 — standardize Functions:** move banking-legislation-tracker to Flex +
  managed identity (drop connection strings), align Python 3.12, shared workspace.
- **P4 — RG taxonomy:** split `bank-data`, rename to the `rg-<project>` scheme.

---

## P1 cleanup runbook

Read-only verification first; destructive commands are clearly marked. Nothing
here is executed for you — run it yourself after reading.

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
