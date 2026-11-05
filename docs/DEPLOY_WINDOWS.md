# Deploying Casework on Windows Server

This guide installs Casework on Windows Server 2016/2019/2022/2025 as a **Windows service**
that starts with the server and restarts if it crashes. It uses:

- **Waitress**, a production web server that runs on Windows (`serve.py`). Flask's built-in
  server (`run.py`) is for development only.
- **NSSM** to run it as a service (Option A), or the built-in Task Scheduler (Option B).

Run every command below in **PowerShell as Administrator**. The examples install to
`C:\Casework` and use port `8080`.

---

## 1. Install Python

1. Download the latest **Python 3.12 or 3.13 Windows installer (64-bit)** from
   <https://www.python.org/downloads/windows/>.
2. Run it and choose **Customize installation**. Then:
   - tick **Add python.exe to PATH**
   - on *Advanced Options*, tick **Install Python for all users** (the service account needs
     to see it; this installs to `C:\Program Files\Python3xx`).
3. Open a **new** PowerShell window and check it worked:

   ```powershell
   python --version
   ```

## 2. Get the code onto the server

**With Git** (install from <https://git-scm.com/download/win> if needed):

```powershell
git clone -b claude/case-management-flask-app-8baxjh https://github.com/gitasksai/Casework.git C:\Casework
```

**Without Git:** on GitHub, open the repository, switch to the branch, click
**Code > Download ZIP**, and extract it so that `C:\Casework\serve.py` exists.

## 3. Create a virtual environment and install dependencies

```powershell
cd C:\Casework
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
mkdir logs, backups -Force
```

## 4. Choose your settings

Generate a secret key (copy the output):

```powershell
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_hex(32))"
```

| Variable | Example | Notes |
|---|---|---|
| `CASEWORK_SECRET_KEY` | *(the value above)* | Required. |
| `CASEWORK_USERNAME` | `casework` | Turns on the login prompt. **Strongly recommended on a server.** |
| `CASEWORK_PASSWORD` | *(a strong password)* | Used with the username above. |
| `CASEWORK_PORT` | `8080` | Port to listen on. |
| `CASEWORK_HOST` | `0.0.0.0` | `0.0.0.0` = reachable from the network; `127.0.0.1` = this server only (use with IIS, step 8). |
| `CASEWORK_DATABASE_URL` | `sqlite:///C:/Casework/instance/casework.db` | Optional. This is the default; note the forward slashes. |
| `CASEWORK_SWARM_AGE_DAYS` / `CASEWORK_SI_AGE_DAYS` | `5` / `15` | Optional thresholds. |

## 5. Test it by hand

```powershell
cd C:\Casework
$env:CASEWORK_SECRET_KEY = "paste-secret-here"
$env:CASEWORK_USERNAME   = "casework"
$env:CASEWORK_PASSWORD   = "choose-a-password"
.\.venv\Scripts\python.exe serve.py
```

You should see `Serving on http://0.0.0.0:8080`. Open <http://localhost:8080> on the server,
log in, and create a test case. Press **Ctrl+C** to stop it.

## 6. Run it as a Windows service

### Option A (recommended): NSSM

1. Download NSSM from <https://nssm.cc/download>, extract it, and copy `win64\nssm.exe` to
   `C:\Windows\System32` (or anywhere on your PATH).
2. Create the service (one setting per line; replace the secret, username and password):

   ```powershell
   nssm install Casework "C:\Casework\.venv\Scripts\python.exe" "C:\Casework\serve.py"
   nssm set Casework AppDirectory "C:\Casework"
   nssm set Casework DisplayName "Casework"
   nssm set Casework Description "Casework case management web app"
   nssm set Casework Start SERVICE_AUTO_START
   nssm set Casework AppEnvironmentExtra "CASEWORK_SECRET_KEY=paste-secret-here" "CASEWORK_USERNAME=casework" "CASEWORK_PASSWORD=choose-a-password" "CASEWORK_PORT=8080"
   nssm set Casework AppStdout "C:\Casework\logs\casework.log"
   nssm set Casework AppStderr "C:\Casework\logs\casework.log"
   nssm set Casework AppRotateFiles 1
   nssm set Casework AppRotateBytes 10485760
   nssm start Casework
   ```

3. Check it is running:

   ```powershell
   Get-Service Casework
   Get-Content C:\Casework\logs\casework.log -Tail 20
   ```

NSSM restarts the app automatically if it exits. Useful commands:
`nssm restart Casework`, `nssm stop Casework`, `nssm edit Casework` (opens a settings
window), `nssm remove Casework confirm`.

### Option B: Task Scheduler (no extra downloads)

1. Create `C:\Casework\start-casework.cmd` containing:

   ```bat
   @echo off
   cd /d C:\Casework
   set CASEWORK_SECRET_KEY=paste-secret-here
   set CASEWORK_USERNAME=casework
   set CASEWORK_PASSWORD=choose-a-password
   set CASEWORK_PORT=8080
   C:\Casework\.venv\Scripts\python.exe serve.py >> C:\Casework\logs\casework.log 2>&1
   ```

2. Lock the file down, since it contains your password:

   ```powershell
   icacls C:\Casework\start-casework.cmd /inheritance:r /grant:r "Administrators:F" "SYSTEM:F"
   ```

3. Register a task that starts at boot, and start it now:

   ```powershell
   $action   = New-ScheduledTaskAction -Execute "C:\Casework\start-casework.cmd"
   $trigger  = New-ScheduledTaskTrigger -AtStartup
   $settings = New-ScheduledTaskSettingsSet -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero)
   Register-ScheduledTask -TaskName "Casework" -Action $action -Trigger $trigger -Settings $settings -User "SYSTEM" -RunLevel Highest
   Start-ScheduledTask -TaskName "Casework"
   ```

## 7. Open the firewall

Allow the port (optionally only from your office network with `-RemoteAddress`):

```powershell
New-NetFirewallRule -DisplayName "Casework (TCP 8080)" -Direction Inbound -Protocol TCP -LocalPort 8080 -Action Allow
# or, limited to one subnet:
# New-NetFirewallRule -DisplayName "Casework (TCP 8080)" -Direction Inbound -Protocol TCP -LocalPort 8080 -RemoteAddress 10.0.0.0/24 -Action Allow
```

From another PC, browse to `http://<server-name-or-ip>:8080`.

## 8. (Recommended) HTTPS with IIS in front

The login uses HTTP Basic authentication, so without HTTPS the password crosses the network
unencrypted. On a trusted internal network that may be acceptable; otherwise put IIS in front:

1. Install IIS, plus **URL Rewrite** and **Application Request Routing (ARR)** from
   <https://www.iis.net/downloads/microsoft/url-rewrite> and
   <https://www.iis.net/downloads/microsoft/application-request-routing>.
2. In IIS Manager, select the server node, open **Application Request Routing Cache >
   Server Proxy Settings**, tick **Enable proxy**, and click Apply.
3. Create a site (e.g. `casework.yourcompany.local`) with an **HTTPS binding** and your
   certificate. Give it an empty folder as its physical path, e.g. `C:\inetpub\casework`.
4. Put this `web.config` in that folder:

   ```xml
   <?xml version="1.0" encoding="UTF-8"?>
   <configuration>
     <system.webServer>
       <rewrite>
         <rules>
           <rule name="Casework" stopProcessing="true">
             <match url="(.*)" />
             <action type="Rewrite" url="http://127.0.0.1:8080/{R:1}" />
           </rule>
         </rules>
       </rewrite>
     </system.webServer>
   </configuration>
   ```

5. Change the app to listen only locally, so it can't be reached around IIS:
   `nssm set Casework AppEnvironmentExtra ... "CASEWORK_HOST=127.0.0.1"` (repeat the other
   variables in the same command, because it replaces the whole list), then
   `nssm restart Casework`.
6. Open port 443 in the firewall instead of 8080, and remove the 8080 rule.

## 9. Back up the database daily

All your data is in one file: `C:\Casework\instance\casework.db`. `backup.py` makes a safe copy
even while the app is running, and deletes copies older than the number of days you give it.
Point it at another disk or a network share if you can:

```powershell
$action  = New-ScheduledTaskAction -Execute "C:\Casework\.venv\Scripts\python.exe" -Argument "C:\Casework\backup.py D:\Backups\Casework 30" -WorkingDirectory "C:\Casework"
$trigger = New-ScheduledTaskTrigger -Daily -At 11pm
Register-ScheduledTask -TaskName "Casework backup" -Action $action -Trigger $trigger -User "SYSTEM" -RunLevel Highest
Start-ScheduledTask -TaskName "Casework backup"     # run once now to check
```

If you set `CASEWORK_DATABASE_URL` to a different location, set it for this task too (or
use a `.cmd` wrapper like in Option B).

**To restore:** stop the service, copy a backup over `C:\Casework\instance\casework.db`,
then start the service.

## 10. Updating to a new version

```powershell
nssm stop Casework                 # or: Stop-ScheduledTask -TaskName Casework
cd C:\Casework
git pull                           # or extract the new ZIP over the folder (keep instance\ and logs\)
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
nssm start Casework                # or: Start-ScheduledTask -TaskName Casework
```

## Troubleshooting

| Symptom | Check |
|---|---|
| Service starts then stops | `Get-Content C:\Casework\logs\casework.log -Tail 50` |
| `python` not found by the service | Use the full path to `.venv\Scripts\python.exe`; make sure Python was installed *for all users*. |
| Port already in use | `netstat -ano \| findstr :8080`, then pick another `CASEWORK_PORT`. |
| Works on the server but not from other PCs | Firewall rule (step 7), and `CASEWORK_HOST` must be `0.0.0.0` if you're not using IIS. |
| Browser keeps asking for a password | Username and password are case-sensitive; check the values in `nssm edit Casework` > *Environment*. |
| 502 error through IIS | The Casework service isn't running, or the port in `web.config` doesn't match `CASEWORK_PORT`. |
