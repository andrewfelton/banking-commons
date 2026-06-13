# Azure architecture (cross-project reference)

The five banking-policy projects share one Azure subscription
(`Azure subscription 1`, `70e0cd03-fbee-44bb-8617-4b2ea3f12837`). This doc is the
single map of what's deployed, what's cruft, and the target layout. It lives in
`banking-commons` because the shared resource (ACS email) is the infra twin of
the shared `banking_commons.email` code.

> Snapshot date: 2026-06-13, **after P2 (shared ACS)**. Re-run the audit commands
> at the bottom if it's been a while.

## Current state

| Project | Compute | Data storage → contents | Email | Resource group(s) |
| --- | --- | --- | --- | --- |
| ai_news_feed | Functions **Flex** (`feltonainews`) | `feltonainews` → `ProcessedPapers` | ACS `acs-banking` (EMAIL_SENDER) | feltonainews |
| banking-legislation-tracker | Functions **Consumption** (`EastUSLinuxDynamicPlan`) | `bankinglegislation` → `TrackedBills`, `TrackerMeta` | ACS `acs-banking` (conn-string) | bank-data |
| bank-filings-pipeline | local cron | `bankdata1` → `FilingsManifest`, `sec-filings` | ACS `acs-banking` | bank-data (storage only) |
| comment_summarization | local launchd | local FS | ACS `acs-banking` | — (local only) |
| congressional-transcripts | local | local FS | — | — |
| _shared_ | — | — | ACS `acs-banking` + managed domain | **rg-banking-shared** |

**All four email senders share one ACS resource** (`acs-banking` in
`rg-banking-shared`). Sender: `DoNotReply@a7665fc6-00a7-47d3-804e-53ee4a14b462.azurecomm.net`.
This is the infra twin of the shared `banking_commons.email` code.

### Removed in P1/P2 — ✅ done 2026-06-13

| Resource | Group | Phase |
| --- | --- | --- |
| `ainewsfeedstorage` (storage) | ai_news_feed | P1 |
| `ainewsfeed` (storage) | ai_news_feed | P1 |
| `ainewsfeed` (App Insights) | ai_news_feed | P1 |
| `ainewsfeed-uami` (managed identity) | ai_news_feed | P1 |
| `regulations1` (storage) + `regulations` RG | regulations | P1 |
| `ainewsfeed` ACS + the whole `ai_news_feed` RG | ai_news_feed | P2 |

The old `ainewsfeed` ACS and its resource group are gone; the new shared ACS
lives in `rg-banking-shared`.

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
- **P2 — shared ACS ✅ done (2026-06-13):** stood up `rg-banking-shared` +
  `acs-banking` + managed domain, repointed all four senders (new sender
  `DoNotReply@a7665fc6-…azurecomm.net`), verified, and deleted the old
  `ainewsfeed` ACS along with its entire `ai_news_feed` RG.
- **P3 — standardize Functions (next):** move banking-legislation-tracker to Flex
  + managed identity (drop connection strings — it's the last sender still using
  one), align Python 3.12, point both apps at a shared Log Analytics workspace.
- **P4 — RG taxonomy:** split `bank-data` into `rg-bank-filings` +
  `rg-banking-legislation`; rename to the `rg-<project>` scheme.

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

## P2 runbook — shared ACS

> ✅ **Executed 2026-06-13.** Verified afterward: `rg-banking-shared/acs-banking`
> is live, all four senders resolve to its endpoint with the new sender address,
> and the old `ainewsfeed` ACS + `ai_news_feed` RG are deleted. Kept for
> reference / reproducibility.

Stands up `acs-banking` in a neutral `rg-banking-shared`, repoints all four
senders, verifies, then retires the old `ainewsfeed` ACS and its RG. A new
Azure-managed domain means a **new sender address** (Step 3); the recipient var
(`DIGEST_RECIPIENT` / `EMAIL_TO`) is unchanged everywhere.

```bash
SUB=70e0cd03-fbee-44bb-8617-4b2ea3f12837
az account set --subscription "$SUB"
SHARED_RG=rg-banking-shared
DATA_LOC=UnitedStates        # mirrors the existing ACS

# 1. Shared RG (region is just for metadata — ACS resources are global)
az group create -n "$SHARED_RG" -l eastus

# 2. Email Communication Service + Azure-managed domain (no DNS setup needed)
az communication email create -n acs-banking -g "$SHARED_RG" \
  --location global --data-location "$DATA_LOC"
az communication email domain create -n AzureManagedDomain -g "$SHARED_RG" \
  --email-service-name acs-banking --location global --domain-management AzureManaged

# 3. >>> GET THE NEW SENDER ADDRESS <<<
#    Managed domains auto-create a 'DoNotReply' sender username, so the full
#    address is DoNotReply@<fromSenderDomain>.
FROM=$(az communication email domain show -n AzureManagedDomain \
  --email-service-name acs-banking -g "$SHARED_RG" --query fromSenderDomain -o tsv)
echo "NEW sender address:  DoNotReply@$FROM"

# 4. Communication Services resource, linked to the domain
DOMAIN_ID=$(az communication email domain show -n AzureManagedDomain \
  --email-service-name acs-banking -g "$SHARED_RG" --query id -o tsv)
az communication create -n acs-banking -g "$SHARED_RG" \
  --location global --data-location "$DATA_LOC" --linked-domains "$DOMAIN_ID"

# 5. New connection string
ACS_CONN=$(az communication list-key -n acs-banking -g "$SHARED_RG" \
  --query primaryConnectionString -o tsv)
SENDER="DoNotReply@$FROM"

# 6. Repoint the two FUNCTION apps (settings take effect on next run):
az functionapp config appsettings set -g feltonainews -n feltonainews --settings \
  AZURE_COMMUNICATION_CONNECTION_STRING="$ACS_CONN" EMAIL_SENDER="$SENDER"
az functionapp config appsettings set -g bank-data -n banking-legislation-tracker --settings \
  ACS_CONNECTION_STRING="$ACS_CONN" ACS_SENDER_ADDRESS="$SENDER"

#    Repoint the two LOCAL apps by editing their .env (var names differ per app):
#      ~/code/comment_summarization/.env   ACS_CONNECTION_STRING + ACS_SENDER_ADDRESS
#      ~/code/bank-filings-pipeline/.env   AZURE_COMMUNICATION_CONNECTION_STRING + EMAIL_SENDER
echo "Set local .env conn string to:"; echo "$ACS_CONN"
echo "Set local .env sender to:      $SENDER"

# 7. VERIFY before deleting anything — send a test through the new ACS:
( cd ~/code/comment_summarization && source .venv/bin/activate && \
  ACS_CONNECTION_STRING="$ACS_CONN" ACS_SENDER_ADDRESS="$SENDER" DIGEST_RECIPIENT="andy.felton@gmail.com" \
  python -c "from banking_commons.email import send_email; print(send_email('P2 ACS test', text='shared acs works', on_config_error='raise', on_send_error='raise'))" )
#   Expect a SendResult(sent=True, status='Succeeded') and an email in your inbox.

# 8. RETIRE the old ACS — ONLY after the test passes AND all four senders are
#    repointed (Functions: confirm next run is green; local: next scheduled run).
#    After P1 the ai_news_feed RG holds only the old ACS + a stray action group,
#    so deleting the whole RG cleans it in one shot:
az group delete -n ai_news_feed --yes
```

Result: `rg-banking-shared/acs-banking` is the single email sender for all four
projects; `ai_news_feed` RG is gone. Update the current-state table and phase
list above when done.

## Audit commands (rebuild this map)

```bash
az group list -o table
az resource list --query "sort_by([].{group:resourceGroup,type:type,name:name},&group)" -o table
# per storage account: data-plane contents
az storage table list     --account-name <acct> --auth-mode login -o tsv
az storage container list --account-name <acct> --auth-mode login -o tsv
```
