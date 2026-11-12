# Playbooks: fast checks by issue family

Read only the section that matches. Each section lists the first checks that split the likely
causes, the facts to ask for, and which logs prove it. Confirm the specifics against the docs
sweep, because steps change between versions.

## Contents
1. Sign-in, SAML, SSO, MFA
2. Extract refresh failures and Tableau Bridge
3. Slow dashboards and performance
4. Connectivity, drivers, credentials
5. Publishing, permissions, content missing
6. Subscriptions, data-driven alerts, email
7. Server install, upgrade, TSM, services down
8. Licensing and activation
9. Embedding and REST API
10. Hyper and extracts on disk
11. Tableau Prep flows
12. Tableau Pulse and metrics

---

## 1. Sign-in, SAML, SSO, MFA
- Scope: one user or all? Server or Cloud? Did a certificate or IdP setting change recently? Expired
  IdP signing certificates are a very common cause of "everyone can't log in".
- Cloud: is the user's authentication type on the site (SAML vs Tableau with MFA) the one they're using?
  Is the user licensed on the site? Is their username exactly the IdP's NameID or email?
- Server SAML: check the clock offset between Server and IdP (assertions expire), the entity ID / ACS URL
  matches, and the IdP metadata is current.
- Quick split: does a local or admin account still work? If yes, the problem is the IdP or user mapping.
  If no, it's the service.
- Logs: a browser **HAR file** of the failed sign-in; Server `vizportal` and `authn`/`samlservice` logs
  around that time.

## 2. Extract refresh failures and Tableau Bridge
- Get the exact error from the job: Cloud **Site Status / Jobs** (or Admin Insights), or Server
  **Background Tasks for Extracts** admin view. The error text says which family it is: credentials,
  timeout, query error, or Bridge client unavailable.
- Credentials: an expired embedded password or OAuth token is the top cause after password rotation.
  Re-embed and test.
- Timeouts: Server `backgrounder` query limit (see `tsm configuration` docs for the backgrounder timeout key);
  Cloud has a fixed extract refresh timeout. Fixes: incremental refresh, extract filters, hide unused fields.
- Bridge: is the client online in Bridge settings, in the right pool, and are its version and drivers current? Is the data
  source in the pool's private network allowlist? Was the client's Windows service account changed?
- Logs: Bridge client logs (see `logs.md`) for the job time; Server `backgrounder` logs.

## 3. Slow dashboards and performance
- Is it slow for everyone or one user, all the time or only at peak hours? Was something published or upgraded?
- Split query time from render time: **Performance Recording** in Desktop or Server. Long "Executing Query" means the
  database or the extract design. Long "Computing Layout" or "Rendering" means the workbook design.
- Common fixes: fewer marks and quick filters, context filters, extracts instead of live, use the Workbook
  Optimizer, avoid row-level calculations on huge sources.
- Server-wide slowness: check the resource use of the `vizqlserver` / `backgrounder` processes, the cache
  settings, and whether backgrounder jobs are competing at peak hours.
- Logs: Performance Recording workbook; Server `vizqlserver` logs (`end-query`, `qp-batch-summary` events with elapsed times).

## 4. Connectivity, drivers, credentials
- Get the database's own error code from the Tableau message. It usually decides the cause: authentication, network, TLS, or permission.
- Check the driver matches the Tableau version and the 32/64-bit requirement on the driver download page.
- Network: can the machine running the query (the Desktop PC, every Server node running backgrounder/vizql, or the Bridge
  client) reach host:port? For Cloud live connections, are Tableau Cloud's IP ranges allowed by the database firewall?
- TLS: expired or untrusted certificates; a corporate proxy that inspects TLS.
- OAuth connectors (Snowflake, BigQuery, Salesforce, Google): has the token been revoked or expired? Re-authenticate.
- Logs: Desktop `log.txt` + `tabprotosrv*.txt`; Server `dataserver`, `vizqlserver`, `backgrounder` logs.

## 5. Publishing, permissions, content missing
- Permissions: use the **effective permissions** view for the user on that content. Check project-level locking
  and group membership. Site role caps capabilities: a Viewer can't publish.
- "Content disappeared": was it moved, deleted, or the owner removed? Check Admin Insights or the TS Events
  admin view, and the recycle bin if the version has one.
- Publish failures: file size limits, a data source that needs credentials embedded, or a version mismatch.
  Desktop newer than Server needs **Save As** to an older version.
- Logs: `vizportal` / `vizqlserver` around the publish time.

## 6. Subscriptions, data-driven alerts, email
- Server: are SMTP settings valid (`tsm` email configuration, test email)? Does the subscriber still have access, and
  does the view need credentials that aren't embedded?
- A subscription for a view with no data, or user filters, can be suppressed or sent blank by design. Check the docs for that version.
- Cloud emails: check the recipient's spam/quarantine, and that the sender domain is allowed.
- Logs: `backgrounder` logs (subscription jobs) for the scheduled time.

## 7. Server install, upgrade, TSM, services down
- First run `tsm status -v` and note which service and node is down or degraded.
- Disk space on the data directory is the most common cause of services failing after a while. Also check memory and
  antivirus scanning the data directory (it should be excluded per docs).
- Upgrade failures: get the exact step from the upgrade script output and log. Check the prerequisites in the upgrade
  docs for the target version. Look for a **backup taken before the upgrade**, so a rollback is possible.
- Logs: `tsm maintenance ziplogs` from the date of the failure; installer/upgrade logs; `tabadmincontroller` and
  `tabadminagent` logs; the failing service's own folder.

## 8. Licensing and activation
- Desktop: product key active and not over its activation count? Offline activation needed? Is it signed in with
  login-based license management?
- Server: `tsm licenses list`. Check whether the license has expired or the user-based capacity is exceeded.
  Check whether core-based licensing doesn't match the hardware.
- Logs: Desktop activation logs in the Logs folder; Server `licenseservice` logs.

## 9. Embedding and REST API
- Embedding: third-party cookie blocking in the browser (Safari, Chrome changes) breaks embedded views without
  Connected Apps or a proper SSO setup. Check Connected Apps or the JWT config, the allowed domains, and the token's `aud`, `sub`,
  `scp` and expiry.
- REST API: get the full error JSON (`summary`, `detail`, `code`). Check the API version against the Server version.
  Check the PAT has not expired or been revoked, since PATs expire when unused.
- Logs: browser HAR and console; Server `vizportal` / `gateway` (httpd) logs for the request.

## 10. Hyper and extracts on disk
- Errors that mention `hyperd`: check disk space and memory on the node, and the extract size.
- Corrupt or failing extracts: try a full refresh, or rebuild from the source.
- Logs: `hyper` logs folder (Server) or `hyperd_*.log` in the Desktop Logs folder.

## 11. Tableau Prep flows
- Does it fail in Prep Builder or only when scheduled (Prep Conductor on Server/Cloud)? Scheduled failures are
  usually credentials, file paths not reachable from Server, or a missing driver on the Server node.
- Logs: Prep Builder `My Tableau Prep Repository/Logs`; Server `backgrounder` / flow processor logs.

## 12. Tableau Pulse and metrics
- Check that Pulse is enabled for the site, the user has access to the metric definition's data source, and the
  data source has the required time dimension. Digest emails depend on the user's follow settings.
- Check the docs sweep. Pulse changes often, so prefer the newest Help pages and release notes.
