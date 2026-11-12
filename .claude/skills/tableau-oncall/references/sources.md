# Sources to sweep

Search every row for each issue. Run the searches in parallel. Use the exact error text or code
in quotes, plus a short symptom phrase, and add the product and version when they help.

| # | Source | What it answers | Search with |
|---|--------|-----------------|-------------|
| 1 | **Salesforce Trust / status** - `status.salesforce.com` (Tableau Cloud pods; `trust.tableau.com` redirects here) | Is there an outage or maintenance on the customer's pod right now? | Open the Tableau product page and find the pod in the site URL (e.g. `prod-useast-a`, `10ax`, `us-west-2b`) |
| 2 | **Salesforce Known Issues** - `issues.salesforce.com` | Confirmed bugs, workarounds, fixed-in version | `site:issues.salesforce.com tableau "<error>"` |
| 3 | **Tableau release notes / resolved issues** - `tableau.com/support/releases` | Was it fixed in a later maintenance release? | `site:tableau.com/support/releases "<symptom>"` and the version page, e.g. `.../releases/server/2024.2.5` |
| 4 | **Tableau Help docs** - `help.tableau.com` (Server: `/current/server/en-us/` or `/server-linux/`, Cloud: `/current/online/`, Desktop: `/current/pro/desktop/`, Prep: `/current/prep/`, Bridge: in `/online/` docs, REST API: `/current/api/rest_api/`, Embedding: `/current/api/embedding_api/`) | How a feature is supposed to work, limits, config steps, `tsm` reference | `site:help.tableau.com "<feature or error>"`. Swap `current` for a version (e.g. `v2023.3`) for older Servers |
| 5 | **Salesforce Help: Tableau Knowledge articles** - `help.salesforce.com` (the old `kb.tableau.com` articles now live here) | Error-specific causes and resolutions | `site:help.salesforce.com tableau "<error code or text>"` |
| 6 | **Tableau Community / Trailblazer Community** - `community.tableau.com` | Other people with the same symptom, workarounds, Ideas | `site:community.tableau.com "<error>"` |
| 7 | **Tableau driver downloads** - `tableau.com/support/drivers` | Correct driver and version for a connector | Look up the connector name |
| 8 | **Tableau on GitHub** - `github.com/tableau` (Tableau Log Viewer, TSC/REST client, connector SDK, server-client-python issues) | API client bugs, log tooling | `site:github.com/tableau "<error>"` |
| 9 | **Data source vendor docs** (Snowflake, Databricks, BigQuery, Redshift, SQL Server, Oracle, SAP, Okta/Azure AD for SAML...) | Database or IdP side errors that Tableau only passes on | Vendor's docs with the database error code |

## Tips

- **Hex error codes** (8 characters, e.g. `1E0B3E4D`, `7F93B9F4`) map to specific failure points.
  Search them exactly. They often find a Knowledge article straight away.
- If the error mentions a **request ID** or a time, keep it for log analysis (see `logs.md`).
- Help docs pages have a version picker. Make sure the page matches the customer's version. Cloud
  always runs the latest version.
- If web search is unavailable, still give the user the ready-made search links, one per source, so
  they can open them in their browser.
- Don't paste customer names, site names or internal hostnames into public searches. Search only the
  error text.
