# Capturing cases from Salesforce with the Chrome extension

The **Casework Capture** extension reads the Salesforce case you have open (case details and
the case feed) and sends it to Casework. Casework sorts every email, comment and post into a
tab, ignores the noise, and shows you a **review screen**. Nothing is saved until you click
**Import**.

## What it does with the case feed

| Feed item | Goes to |
|---|---|
| Your first email/post to the customer | **Initial Response** |
| Your questions to the customer (lines ending in `?`, or a numbered list after "please confirm/provide…") | **Scoping Q&A**, with the customer's next reply as the answer |
| Call / meeting / remote session summaries | **Meeting Summaries** |
| Your internal (`To: Internal`) notes and technical updates (logs, errors, tests, workaround…) | **Troubleshooting** |
| Other customer messages and updates | **Other Notes** |
| "Any update?", "Just following up", "Gentle reminder", "We will close this case…" | Ignored: *Follow-up / reminder* |
| "Thank you for sharing… I will check and update you" (short, no new information) | Ignored: *Acknowledgement* |
| Automated posts ("System Generated Feed", auto-responses) | Ignored: *Automated / system message* |
| "changed Status from New to Working" | Ignored: *Status or field change* |

Email signatures ("Best regards, …"), greetings ("Hi Alex,") and quoted earlier messages
("On … wrote:", "-----Original Message-----", lines starting with `>`) are stripped.

From the case details it fills in: case number, subject, customer (Account), product (Product &
Topic + Product Feature), version and operating system (from fields, or found in the
description), severity, status, opened date and description.

Re-capturing the same case later is safe: items already imported are recognised and skipped,
so only new activity is offered.

Everything on the review screen can be changed: untick items, move them to another tab, tick
ignored items you want after all, and edit the case field values.

## 1. Set an API token on the server

The extension authenticates with a token instead of your Casework password. Generate one:

```powershell
cd C:\Projects\Casework
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(32))"
```

- **Running Casework from VS Code on your PC:** if you haven't set a username/password, no token
  is needed. Otherwise add `"CASEWORK_API_TOKEN": "<token>"` to the `"env"` block of the launch
  configuration you use in `.vscode\launch.json`.
- **On the Windows Server service:** add `CASEWORK_API_TOKEN=<token>` to the service's environment
  (`nssm edit Casework` > *Environment* tab, or the `.cmd` file for Task Scheduler) and restart it.

## 2. Install the extension in Chrome

1. Open **chrome://extensions** in Chrome.
2. Turn on **Developer mode** (top-right switch).
3. Click **Load unpacked** and choose the folder **`C:\Projects\Casework\chrome-extension`**.
4. Click the puzzle-piece icon in the toolbar and **pin** *Casework Capture* so its icon is
   always visible.

The settings page opens automatically the first time.

> If *Developer mode* or *Load unpacked* is greyed out, your company's Chrome policy blocks
> unpacked extensions. Ask IT to allow it, or to deploy the `chrome-extension` folder for you.
> Microsoft Edge works the same way (**edge://extensions**).

## 3. Settings

Right-click the extension icon > **Options** (or click **Settings** in its popup):

| Setting | What to enter |
|---|---|
| Casework server address | Where you open Casework, e.g. `http://127.0.0.1:5000` (VS Code) or `https://casework.mycompany.local:8443` (server) |
| API token | The token from step 1 (empty if your Casework has no login) |
| Your name as shown in Salesforce | e.g. `Sathishkumar Ashok`. This tells your messages apart from the customer's. If empty, the Case Owner is used. |

Click **Test connection**. It should say **Connected to Casework**.

If you use HTTPS with a self-signed certificate, this PC must trust it first (see
[DEPLOY_WINDOWS.md](DEPLOY_WINDOWS.md), step 4). Otherwise the test can't connect.

## 4. Capture a case

1. In Salesforce, open the case. On the feed, select **All Updates** (as in your Support Console)
   so emails, comments and posts are all listed.
2. Click the **Casework Capture** icon and then **Capture this case**.
   - With *Expand "show more" posts first* ticked, it clicks **Show More** on long posts and
     **View More** at the bottom of the feed (a few rounds) so the full history is captured.
3. A new tab opens with the **Review import** screen. Check the case fields and items, then click
   **Import into Casework**.

You land on the case's **Timeline** tab with everything imported. Capture again whenever the case
has new activity; only new items are offered.

## Tuning what gets ignored

The rules live at the top of **`casework/importer.py`** as plain lists of phrases (regular
expressions), e.g. `FOLLOW_UP_TEXT`, `ACKNOWLEDGEMENT_TEXT`, `AUTOMATION_AUTHORS`,
`MEETING_TEXT`, `TECHNICAL_TEXT`. Add a phrase your team uses, restart Casework, and capture again.
Run `pytest` afterwards to make sure nothing else changed.

## Troubleshooting

| Problem | What to do |
|---|---|
| "No feed items were found" | Scroll to the feed and select *All Updates*, then capture again. If it still happens, see "Page structure" below. |
| Fields or posts are missing | Salesforce only shows what's on screen. Open the *Details* tab for fields, and the feed for posts. |
| "Could not reach the Casework server" | Casework isn't running, the address is wrong, or (HTTPS) the certificate isn't trusted on this PC. Open the address in Chrome to check. |
| "Invalid or missing API token" | The token in the extension doesn't match `CASEWORK_API_TOKEN` on the server. |
| "This server has a login, so set CASEWORK_API_TOKEN" | Set the token on the server (step 1) and in the extension. |
| My messages show as "Customer" | Set *Your name as shown in Salesforce* exactly as it appears on your posts. |
| Dates are wrong (day and month swapped) | Casework works out day/month order from the page. If it's wrong, fix the date on the review screen. |
| Something was put in the wrong tab | Change it on the review screen. If it keeps happening, add phrases to the lists in `importer.py`. |

**Page structure (no case data):** Salesforce changes its page layout from time to time. If
capture stops finding things, click **Download page structure** in the extension popup. It saves
`casework-page-structure.json` with element names and counts only (no case text or customer
data), which is enough to update the selectors at the top of `chrome-extension/extractor.js`.

## Data handling

Captured cases contain customer names, email addresses and case content. Keep Casework on a
machine your company approves for customer data, protect it with a login and HTTPS (see
[DEPLOY_WINDOWS.md](DEPLOY_WINDOWS.md)), and check that this fits your company's data-handling
policy.
