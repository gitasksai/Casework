# Tableau logs: where they are, how to collect, what to look for

Ask for the **smallest** set that can prove the cause: one machine, one time window (the failure
time ±30 min), plus the request ID or job ID if the customer has it. Check paths and commands against the
Help docs for the customer's version. Run `tsm <command> --help` when unsure of an option.

## Tableau Desktop
- Windows: `Documents\My Tableau Repository\Logs\`. Mac: `~/Documents/My Tableau Repository/Logs/`.
- Key files: `log.txt` (main, JSON lines), `tabprotosrv*.txt` (connections/drivers), `hyperd*.log`
  (extracts), crash dumps in `Logs\crashdumps` or the OS crash folder.
- Ask the customer to reproduce, then zip the whole `Logs` folder straight after.
- Performance issues: also a **Performance Recording** (Help > Settings and Performance > Start Performance Recording).

## Tableau Server (TSM, 2018.2 and later)
- Collect: `tsm maintenance ziplogs -m <mm/dd/yyyy> -f <name>.zip`. `-m` sets the earliest date, so keep it tight.
  Add Postgres data or dumps only if support specifically asks. The archive lands in the data directory under
  `tabsvc/files/log-archives/`.
- Live logs: Windows `C:\ProgramData\Tableau\Tableau Server\data\tabsvc\logs\`. Linux
  `/var/opt/tableau/tableau_server/data/tabsvc/logs/`. There is one folder per service.
- Which folder for which symptom:
  - `vizqlserver`: viewing dashboards, rendering, live queries, sessions (JSON lines; `end-query`, `qp-batch-summary`, `exception`)
  - `backgrounder`: extract refreshes, subscriptions, flows, scheduled jobs
  - `vizportal`: web UI, sign-in, REST API, permissions, publishing
  - `httpd` / `gateway`: access log of every request (status codes, request IDs, durations)
  - `dataserver`: published data source connections
  - `hyper`: extract engine
  - `tabadmincontroller`, `tabadminagent`, `clustercontroller`, `coordinationservice`: TSM, topology, upgrades, failover
  - `pgsql`: repository database
  - `filestore`: extract file movement between nodes
- Server health: `tsm status -v` (paste it into the case). Admin views: Background Tasks, Performance of Views, Stats for Space Usage.
- **Request ID**: every web request gets a unique ID in the `httpd` access log. The same ID appears as `req`
  in the `vizqlserver`/`vizportal` JSON logs. Use it to follow one failed click through every service.
- Viewer: the open-source **Tableau Log Viewer** (github.com/tableau/tableau-log-viewer) reads the JSON logs.

## Tableau Cloud
- There are no server logs for customers. Use **Site Status / Jobs**, **Admin Insights**, and the **Activity Log**
  (with Advanced Management) for events and errors.
- Client side: a browser **HAR file** plus console screenshot for web issues; Desktop logs for publish and connect issues;
  Bridge logs for Bridge refreshes.

## Tableau Bridge
- Windows: `Documents\My Tableau Bridge Repository\Logs\` (as the user the Bridge service runs as). Key
  files: `stdout_jprotocolserver*`, `tabbridgeclijob*`, `tabprotosrv*`, `jprotocolserver*`.
- Include the Bridge client version and the job time (UTC) from Cloud's Jobs page.

## Tableau Prep Builder
- `Documents\My Tableau Prep Repository\Logs\`. For scheduled flows on Server, see the `backgrounder` logs.

## Reading Tableau JSON log lines
Each line looks like:
`{"ts":"2026-11-12T10:15:03.123","pid":1234,"tid":"1a2b","sev":"error","req":"Y3x...","sess":"5F2...","site":"Sales","user":"jdoe","k":"exception","v":{...}}`
- `sev`: severity (`fatal`, `error`, `warn`, `info`, `debug`). `k`: event key. `v`: payload.
- `ts` is the **server's local time** unless the logs say otherwise. Line it up with the customer's time zone.

## Running the scanner
```bash
python scripts/scan_logs.py logs.zip --since "2026-11-12 09:30" --until "2026-11-12 11:00"
python scripts/scan_logs.py ./Logs --req Y3xAbc123            # follow one request
python scripts/scan_logs.py ./tabsvc/logs --grep "timeout" --top 15
```
It reads folders, single files and `.zip` archives (zipped files are read in memory, never extracted).
Then open the raw lines it points to (file:line) to confirm before you conclude.
