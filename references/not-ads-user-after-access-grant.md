# NOT_ADS_USER After Access Grant

Use this reference when a user says the Google Ads OAuth user was added, but `gads auth-check` still reports `NOT_ADS_USER`.

## Meaning

`NOT_ADS_USER` means the OAuth identity that generated the token is still not recognized by Google Ads as attached to any Ads account. Check the configured account surfaces in `~/.google-ads-cli/.env`:

- MCC/login customer: `GOOGLE_ADS_LOGIN_CUSTOMER_ID`
- Customer: `GOOGLE_ADS_CUSTOMER_ID`

Do not assume the access grant succeeded just because someone says the user was added. Google Ads may require the invitation to be accepted by the OAuth user, or the user may have been added to the wrong place.

## Verification sequence

1. Run:

   ```bash
   gads auth-check
   gads auth-doctor --show-email
   gads completion-audit
   ```

2. Confirm the OAuth email shown by `auth-doctor --show-email` is the exact email that received Google Ads access.

3. If `NOT_ADS_USER` persists after the claimed grant, explain the likely causes plainly:

   - The invite was sent but not accepted from that Google account.
   - A different email was added than the OAuth email.
   - The email was added in Google Workspace/Google Cloud but not to Google Ads.
   - The email was added to the wrong Google Ads account rather than the configured MCC or customer.

4. If you suspect a bad login-customer header, compare Google Ads `customers:listAccessibleCustomers` with no login header and with the configured login/customer headers. If all variants return `NOT_ADS_USER`, the blocker is account attachment/acceptance, not the `login_customer_id` setting.

## Operator response pattern

Be concise and action-oriented:

- State that Google Ads CLI credentials, refresh token, and scope are working if `auth-doctor` says so.
- State that Google Ads still rejects the OAuth identity as `NOT_ADS_USER`.
- Tell the user exactly which email must be added/accepted and where.
- Offer to run `gads post-auth-bootstrap` immediately after they confirm the invite is accepted.

Do not run native bootstrap while `auth-check` is still blocked; it will only produce the same blocked state.
