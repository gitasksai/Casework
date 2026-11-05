# Deploying Casework on Windows Server

This guide installs Casework on Windows Server 2016/2019/2022/2025 as a **Windows service**
that serves **HTTPS directly from Python**, with no IIS needed. It starts with the server and
restarts if it crashes. It uses:

- **Cheroot**, a production web server written in Python that runs on Windows and handles
  HTTPS encryption itself (`serve.py`). Flask's built-in server (`run.py`) is for development only.
- **NSSM** to run it as a service (Option A), or the built-in Task Scheduler (Option B).

Run every command below in **PowerShell as Administrator**. The examples install to
`C:\Casework` and use port `8443`.

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

## 4. Get an HTTPS certificate

Browsers only trust a certificate whose name matches the address users type, such as
`https://casework.mycompany.local:8443` or `https://10.0.0.25:8443`. Decide that address first.

### Option 1: certificate from your company's certificate authority (best)

If your organisation has its own certificate authority (often Active Directory Certificate
Services), ask for a **web server certificate** for the address above, delivered as a
**.pfx file with the private key**. You can also export one from the Windows certificate store:
`certlm.msc` > *Personal* > *Certificates* > right-click the certificate > *All Tasks* >
*Export* > *Yes, export the private key* > *.PFX*.

Then convert it into the files Python needs:

```powershell
cd C:\Casework
.\.venv\Scripts\python.exe tls_cert.py from-pfx C:\path\to\casework.pfx
```

You'll be asked for the .pfx password. Company PCs already trust your certificate authority,
so users get no browser warnings.

### Option 2: self-signed certificate (no certificate authority needed)

```powershell
cd C:\Casework
.\.venv\Scripts\python.exe tls_cert.py self-signed --name casework.mycompany.local --ip 10.0.0.25
```

Use your real DNS name and/or IP address (`--name` and `--ip` can be repeated). The server's
own hostname and `localhost` are added automatically. The certificate is valid for 2 years
(`--days` changes that).

The connection is fully encrypted, but browsers will show a warning **until each user's PC
trusts the certificate**. To trust it, copy `C:\Casework\certs\casework.crt` to the PC, then
either:

- double-click it > **Install Certificate** > *Local Machine* > *Place all certificates in
  the following store* > **Trusted Root Certification Authorities**, or
- run this in PowerShell as Administrator on that PC:
  `Import-Certificate -FilePath .\casework.crt -CertStoreLocation Cert:\LocalMachine\Root`

For many PCs, a domain admin can push it with Group Policy: *Computer Configuration > Policies >
Windows Settings > Security Settings > Public Key Policies > Trusted Root Certification
Authorities > Import*.

### Protect the private key

Either option writes `C:\Casework\certs\cert.pem` and `C:\Casework\certs\key.pem`. Anyone who
can read `key.pem` can impersonate your server, so restrict the folder to administrators and
the service account:

```powershell
icacls C:\Casework\certs /inheritance:r /grant:r "Administrators:(OI)(CI)F" "SYSTEM:(OI)(CI)F"
```

## 5. Choose your settings

Generate a secret key (copy the output):

```powershell
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_hex(32))"
```

| Variable | Example | Notes |
|---|---|---|
| `CASEWORK_SECRET_KEY` | *(the value above)* | Required. |
| `CASEWORK_SSL_CERT` | `C:\Casework\certs\cert.pem` | Turns on HTTPS (with the key below). |
| `CASEWORK_SSL_KEY` | `C:\Casework\certs\key.pem` | |
| `CASEWORK_USERNAME` | `casework` | Turns on the login prompt. **Strongly recommended.** |
| `CASEWORK_PASSWORD` | *(a strong password)* | Used with the username above. |
| `CASEWORK_PORT` | `8443` | Default is 8443 with HTTPS. Use `443` so users don't have to type a port, as long as nothing else on the server uses 443. |
| `CASEWORK_HOST` | `0.0.0.0` | `0.0.0.0` = reachable from the network; `127.0.0.1` = this server only. |
| `CASEWORK_DATABASE_URL` | `sqlite:///C:/Casework/instance/casework.db` | Optional. This is the default; note the forward slashes. |
| `CASEWORK_SWARM_AGE_DAYS` / `CASEWORK_SI_AGE_DAYS` | `5` / `15` | Optional thresholds. |

## 6. Test it by hand

```powershell
cd C:\Casework
$env:CASEWORK_SECRET_KEY = "paste-secret-here"
$env:CASEWORK_SSL_CERT   = "C:\Casework\certs\cert.pem"
$env:CASEWORK_SSL_KEY    = "C:\Casework\certs\key.pem"
$env:CASEWORK_USERNAME   = "casework"
$env:CASEWORK_PASSWORD   = "choose-a-password"
.\.venv\Scripts\python.exe serve.py
```

You should see `Casework listening on https://0.0.0.0:8443`. Open
**https**://localhost:8443 on the server, log in, and create a test case. Press **Ctrl+C**
to stop it.

> Users must type `https://`. Plain `http://` to this port won't load, because the port only
> speaks HTTPS.

## 7. Run it as a Windows service

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
   nssm set Casework AppEnvironmentExtra "CASEWORK_SECRET_KEY=paste-secret-here" "CASEWORK_SSL_CERT=C:\Casework\certs\cert.pem" "CASEWORK_SSL_KEY=C:\Casework\certs\key.pem" "CASEWORK_USERNAME=casework" "CASEWORK_PASSWORD=choose-a-password" "CASEWORK_PORT=8443"
   nssm set Casework AppStdout "C:\Casework\logs\casework.log"
   nssm set Casework AppStderr "C:\Casework\logs\casework.log"
   nssm set Casework AppRotateFiles 1
   nssm set Casework AppRotateBytes 10485760
   nssm start Casework
   ```

   `AppEnvironmentExtra` replaces the whole list each time, so to change one value later,
   repeat all of them (or use `nssm edit Casework` > *Environment* tab).

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
   set CASEWORK_SSL_CERT=C:\Casework\certs\cert.pem
   set CASEWORK_SSL_KEY=C:\Casework\certs\key.pem
   set CASEWORK_USERNAME=casework
   set CASEWORK_PASSWORD=choose-a-password
   set CASEWORK_PORT=8443
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

## 8. Open the firewall

Allow the port (optionally only from your office network with `-RemoteAddress`):

```powershell
New-NetFirewallRule -DisplayName "Casework HTTPS (TCP 8443)" -Direction Inbound -Protocol TCP -LocalPort 8443 -Action Allow
# or, limited to one subnet:
# New-NetFirewallRule -DisplayName "Casework HTTPS (TCP 8443)" -Direction Inbound -Protocol TCP -LocalPort 8443 -RemoteAddress 10.0.0.0/24 -Action Allow
```

From another PC, browse to `https://<the name or IP in your certificate>:8443`.

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
use a `.cmd` wrapper like in Option B). Also keep a copy of `C:\Casework\certs` somewhere safe.

**To restore:** stop the service, copy a backup over `C:\Casework\instance\casework.db`,
then start the service.

## 10. Renewing the certificate

Check the expiry date printed by `tls_cert.py` (or open `cert.pem`) and put a reminder in
your calendar. To renew, run the same `tls_cert.py` command again with a new .pfx (or a
new self-signed certificate, which users must trust again), then `nssm restart Casework`.

## 11. Updating to a new version

```powershell
nssm stop Casework                 # or: Stop-ScheduledTask -TaskName Casework
cd C:\Casework
git pull                           # or extract the new ZIP over the folder (keep instance\, certs\ and logs\)
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
nssm start Casework                # or: Start-ScheduledTask -TaskName Casework
```

## Troubleshooting

| Symptom | Check |
|---|---|
| Service starts then stops | `Get-Content C:\Casework\logs\casework.log -Tail 50` |
| Log says `HTTPS needs both CASEWORK_SSL_CERT and CASEWORK_SSL_KEY` | The paths in the service's environment are wrong, or the files don't exist. |
| Browser says "Your connection isn't private" / `NET::ERR_CERT_AUTHORITY_INVALID` | The self-signed certificate isn't trusted on that PC yet (step 4, Option 2). |
| `NET::ERR_CERT_COMMON_NAME_INVALID` | The address typed isn't in the certificate. Re-run `tls_cert.py` including that name/IP, then restart. |
| Page doesn't load at all | You typed `http://` instead of `https://`; or a firewall rule is missing (step 8). |
| `python` not found by the service | Use the full path to `.venv\Scripts\python.exe`; make sure Python was installed *for all users*. |
| Port already in use | `netstat -ano \| findstr :8443`, then pick another `CASEWORK_PORT`. |
| Browser keeps asking for a password | Username and password are case-sensitive; check the values in `nssm edit Casework` > *Environment*. |
