# Install Ripcars Gate independently

This package installs Gate only. It does not install ticket, moderation or holder bots. Other bot services and their data remain unchanged.

Application code lives under `/opt/ripcars-gate`. The service runs as the restricted `ripcarsgate` user, including when the downloaded package was placed in `/root`.

## 1. Create the Discord application

Create a separate application named `Ripcars Gate` in the Discord Developer Portal. Store its own token in the VPS configuration file.

Enable Server Members Intent and Message Content Intent on the Bot page. Presence Intent is not required.

In the OAuth2 URL Generator, select `bot` and `applications.commands`. Initial provisioning creates Admin and Team roles and channel overwrites, so invite Gate with Administrator for that setup. Its bot role must sit above the roles it creates and assigns. Invite future bots separately.

## 2. Upload from Windows

Download the TAR package and its `RIPCARS_GATE_SHA256SUMS.txt` into this directory:

```text
C:\Users\macbook\Desktop\files
```

Run these commands in PowerShell. Enter the address or SSH alias of your VPS. The example SSH account is `memecult`; replace it if your account differs.

```powershell
Set-Location 'C:\Users\macbook\Desktop\files'
Get-FileHash '.\ripcars-gate-1.0.1.tar.gz' -Algorithm SHA256
$RipcarsVps = Read-Host 'VPS IP or SSH alias'
scp '.\ripcars-gate-1.0.1.tar.gz' '.\RIPCARS_GATE_SHA256SUMS.txt' "memecult@${RipcarsVps}:/tmp/"
ssh "memecult@${RipcarsVps}"
```

If the package is already on the VPS or in `/root`, adjust the source path in the next step to its actual location.

## 3. Check the transfer and install

In the SSH session:

```bash
cd /tmp
sha256sum ripcars-gate-1.0.1.tar.gz
cat RIPCARS_GATE_SHA256SUMS.txt
```

The TAR checksum must match its row in `RIPCARS_GATE_SHA256SUMS.txt`. ZIP contains the same source for convenient inspection. These installation steps use TAR.

```bash
sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip fonts-dejavu-core
RIPCARS_UNPACK_DIR=$(mktemp -d /tmp/ripcars-gate-release.XXXXXX)
tar -xzf /tmp/ripcars-gate-1.0.1.tar.gz -C "$RIPCARS_UNPACK_DIR"
sudo bash "$RIPCARS_UNPACK_DIR/ripcars-gate/scripts/install.sh" "$RIPCARS_UNPACK_DIR/ripcars-gate"
```

The installer installs dependencies and runs the complete suite. A failed check prevents activation of the new release. It does not start companion bots.

## 4. Configure the token and start the service

```bash
sudo nano /etc/ripcars-gate.env
```

Set `DISCORD_TOKEN` to this application's token and `GUILD_ID` to the new server's numeric ID. Keep the two database paths at their default values.

```text
DISCORD_TOKEN=YOUR_RIPCARS_GATE_TOKEN
GUILD_ID=YOUR_SERVER_ID
DB_PATH=/var/lib/ripcars-gate/gate.sqlite3
COORDINATION_PATH=/var/lib/ripcars-bots/coordination.sqlite3
```

After saving:

```bash
sudo systemctl enable --now ripcars-gate
sudo systemctl status ripcars-gate --no-pager -l
sudo journalctl -u ripcars-gate -n 80 --no-pager -l
```

Wait for `online as` with version `1.0.1`. A running service does not open member entry. Entry starts disabled inside Discord.

## 5. Build the server from Discord

Run `/gate panel`.

Server setup → Preview setup → Apply setup.

Review the result file. Resolve FAILED, BLOCKED, CONFLICT and REVIEW items. A same-name role or channel is not adopted automatically. Bind its exact ID under Resources, then preview again.

Rippers has no enabled server-wide permission bits. Each managed channel receives its own complete overwrite policy, including history access where permitted. Owners Chat is restricted to OG and staff. Holder Verification is hidden from ordinary members and OG. Open and Closed are initially staff-only.

Choose Publish panels in Server setup, then check `/gate health`. After resolving blockers, use Entry & CAPTCHA > Activate / Pause to open entry.

Trades and Hot Wheels IRL default to ordinary text channels allowing text, images and links. Their types are editable. Forums require Discord Community. Replacing an existing channel requires binding the new ID and explicit administrator review.

gCARS does not allow direct member messages. Members use Submit text; Gate publishes the submission with their display name and ID. Its persistent per-member cooldown is 24 hours. Content uses native two-hour slowmode.

The ticket bot is not installed by Gate. Ticket displays a preparation message. Gate does not create or manage individual tickets.

## 6. Test before opening the server

Follow `ACCEPTANCE.md` with an ordinary account without Admin or Moderator.

Pass CAPTCHA and click Finish without answering a question. No member role should be granted. Answer one enabled question and click Finish again. Rippers should now be granted and permitted channel history should become visible.

Owner and Administrator bypass channel restrictions. Use an ordinary account to test member permissions.

## 7. Daily management

```bash
sudo systemctl restart ripcars-gate
sudo journalctl -u ripcars-gate -f
```

Edit messages, questions, roles, color, channel names and access from the panel. Managed structural changes apply at the next monitoring pass. External manual changes are preserved and flagged for review. Keep current pins them; Restore template explicitly reapplies the managed template after confirmation.

Daily backups cover both databases, with seven retained copies per database. Health > Backup now creates an immediate backup. Errors and health are available in Discord. If the log channel is inaccessible, details remain in the service journal.

## 8. Update or roll back

Run the same installer against the new package directory, then:

```bash
sudo systemctl restart ripcars-gate
sudo systemctl status ripcars-gate --no-pager -l
```

If an earlier release exists on this VPS, roll back code with:

```bash
sudo bash /opt/ripcars-gate/current/scripts/rollback.sh
```

Code rollback does not restore member data or undo Discord changes. Configuration history in the panel is separate.

## Package validation status

All 52 tests passed with Python, the real discord.py SDK and real SQLite. No tests were skipped. Discord API requests and transport errors were mocked. The installer reruns all 52 tests on the VPS. Live Discord access, actual guild permissions and production systemd operation remain installation acceptance checks.
