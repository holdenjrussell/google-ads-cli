# Unattended Google Ads reads

The warehouse can use a service account granted **Read-only** access to its
Google Ads manager. Keep `GOOGLE_ADS_LOGIN_CUSTOMER_ID` set to that manager.
No domain-wide delegation is required. Google documents the direct grant in
its [service-account workflow](https://developers.google.com/google-ads/api/docs/oauth/service-accounts).
Read-only access supports campaign reports; see
[access levels](https://support.google.com/google-ads/answer/9978556).

Store the JSON key outside Git, in an owned regular file with mode `0600`.
Set `GOOGLE_ADS_JSON_KEY_FILE_PATH` to that path. Tokens refresh in memory;
the key and token never appear in canary output.

`GOOGLE_ADS_AUTH_MODE=oauth` is the default and preserves existing operator
commands. `service_account` requires the new credential. `auto` is reserved
for read-only sync jobs: it tries the service account, then preserved OAuth
credentials on credential or permission failures. Auto mode rejects mutation
endpoints. Canceled accounts and developer-token errors never trigger a
credential retry.

Run `gads auth-canary --receipt /secure/path/auth-canary.json` daily before
the producer. It calls `listAccessibleCustomers` and a customer status query
for every account in `GOOGLE_ADS_CUSTOMER_IDS` or
`GOOGLE_ADS_CUSTOMER_ACCOUNTS_FILE`, using both credentials separately. Its
stable issue ID is `CGK-GADS-ACCESS`; account labels are one-way hashes.
The exit code is nonzero when the primary credential or any expected account
fails, even if OAuth works. The command never sends a message or writes to
the warehouse. Connect its exit code to the existing scheduler alert wrapper.

For `CUSTOMER_NOT_ENABLED`, inspect the manager's `customer_client.status`.
Changing credentials cannot enable a canceled account. Keep the expected
account in the canary and escalate the account-state decision; do not remove
it to make monitoring pass. Google describes this error in
[common errors](https://developers.google.com/google-ads/api/docs/get-started/common-errors).

If the key or Ads grant is lost, auto mode continues eligible reads with the
preserved OAuth credential while the canary reports the primary failure.
Restore the same service account's access or replace its key through the
credential store, then rerun the canary and the producer under its existing
lock. Do not rotate keys or change users during routine canary runs.
