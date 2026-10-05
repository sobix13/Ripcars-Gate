# Ripcars Gate 1.0.2
## Repository files and installation packages

This repository contains the complete 1.0.2 source, tests, dependency files, installation/rollback scripts, systemd service, settings examples and English operational documentation.

| File or directory | Purpose |
| --- | --- |
| [DEPLOYMENT.md](DEPLOYMENT.md) | English Windows-to-VPS installation and Discord setup steps |
| [ACCEPTANCE.md](ACCEPTANCE.md) | Live server acceptance checklist |
| [COORDINATION.md](COORDINATION.md) | Cross-bot ownership and integration protocol |
| [TEST_RESULTS.txt](TEST_RESULTS.txt) | Actual offline verification output |
| [VALIDATION.json](VALIDATION.json) | Machine-readable validation status |
| [requirements.txt](requirements.txt) | Runtime requirements |
| [.env.example](.env.example) | Token and server configuration placeholders |
| [scripts/install.sh](scripts/install.sh) | Isolated release installation with tests |
| [scripts/rollback.sh](scripts/rollback.sh) | Code rollback |
| [ripcars-gate.service](ripcars-gate.service) | Non-root systemd service |
| [tests](tests) | Complete offline suite |
| [releases/1.0.2](releases/1.0.2) | English TAR/ZIP packages, checksums and matching guides |

The source and archives contain no credentials, member databases or virtual environments. Installation excludes Git metadata, previous packaged releases and runtime state. Version 1.0.2 fixes shared coordination and protects foreign resource ownership; member entry requirements are unchanged.

See [SUITE_DEPLOYMENT.md](SUITE_DEPLOYMENT.md) and [SUITE_TEST_RESULTS.txt](SUITE_TEST_RESULTS.txt) for the compatible four-bot versions, rollout and multi-process test evidence. All four ship identical `ripcars_coordination.py`.

```bash
git clone https://github.com/sobix13/Ripcars-Gate.git
cd Ripcars-Gate
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
bash run_tests.sh
```

For VPS installation from this checkout, follow [DEPLOYMENT.md](DEPLOYMENT.md) and replace its archive extraction step with the clone above. Run `sudo bash scripts/install.sh "$PWD"` from the checkout, configure the private environment file, and start only this bot's service as described in the guide.

Also included: [server-blueprint.json](server-blueprint.json) and [permissions.csv](permissions.csv).


Standalone server provisioning and member entry for Rip Cars. No companion bot, ticket engine, moderation engine, wallet connection, or holder service is required.

Compatibility update: a chat-filter deletion that receives NotFound because another bot already deleted the message returns quietly. Forbidden and other genuine failures still surface. Membership, questions, role assignment and database schema are unchanged.

## Entry

New member → image CAPTCHA → at least one enabled question answered → Finish and join → Rippers.

The remaining questions are optional. A successful CAPTCHA alone never grants Rippers. Invalid answers, stale CAPTCHA submissions, expired challenges, and failed role grants do not mark entry complete. Progress survives a process restart. Rejoining resets entry but retains the previously collected profile data.

Defaults: 6 characters, 5-minute image expiry, 3 wrong attempts, 10-minute lock, 30 minutes to finish questions. No automatic kick or ban.

## Permissions

Rippers has zero server-wide permission bits. Every managed channel receives an explicit access policy, including View Channel and Read Message History. Granting additional unrelated roles to a member can change their effective access; Gate protects and reports changes to its own managed resources rather than rewriting outside roles.

Before entry, only Rules, Verification, FAQ, and Official Links are visible. Public channels are read-only. After entry, all ordinary community channels are visible with history. Owners Chat requires OG; OG is assigned manually by an admin. Holder Verification is staff-only. Ticket categories and operational logs are staff-only.

Members never receive Manage Roles, Manage Channels, Manage Messages, Manage Webhooks, Manage Threads, Mention Everyone, private thread creation, or public responses from user-installed external apps. Read-only channels also deny thread replies and thread creation.

Moderator receives reading access across the managed server, deletion, thread moderation, timeout, kick, ban, audit-log access, and nickname moderation. Moderation still obeys Discord role hierarchy. Admin and Team receive Administrator. During the first complete setup, roles are ordered as Team > Admin > Moderator > OG > Rippers > optional claim roles, below the Gate bot's role. Existing role positions are preserved. Accounts are not automatically assigned staff roles.

Text and image channels reject non-image uploads through the bot's message filter. Denying Embed Links disables previews, not the URL itself. The no-link filter runs while Gate is online and can delete a disallowed message after it appears. It is a basic pattern filter, not a universal anti-evasion engine. Members with moderation access are exempt.

gCARS uses a persistent Submit text button and modal. Members cannot send directly. A successful submission is published by the bot with the member's display name and ID. The 24-hour per-member cooldown survives restarts. URLs, files, and mentions are rejected. Content uses native 2-hour slowmode.

Trades and Hot Wheels IRL default to ordinary text channels with text, images, and links. Their type and access are editable. Forum channels require Discord Community to be enabled; changing an existing channel's type requires explicit ID binding to a matching replacement. Gate never deletes a channel to perform a type conversion.

## Admin center

Use `/gate panel`. Sections: Server setup; Entry & CAPTCHA; Questions; Messages; Brand & roles; Channels & access; Resources & manual changes; Future bots; Health & troubleshooting; Member data & history; Guide.

Server setup has Preview and Apply. Public panels are posted or edited by recorded message ID, so repeated publishing does not create duplicates while the recorded message exists. Entry stays paused until an admin publishes panels and resolves activation blockers.

Structural changes to active Gate-managed resources are applied at the next 60-second monitoring pass. Unknown resources, deleted managed resources, partial updates, and external changes are not silently overwritten. Use resource review to Keep current (pin it) or Restore template (explicitly reapply managed values). Bind existing IDs to adopt a same-name object.

Brand name, website, burgundy color, role names, channel names, topics, types, access groups, posting modes, image/link allowances, cooldowns, CAPTCHA policy, questions, and public texts are editable in Discord. Staff permission presets remain fixed to avoid turning ordinary claim roles into privileged roles through the UI.

`/gate health` is available to staff. `/gate guide` is available to members. Member data export and settings history are admin-only. Settings restore pauses entry and requires review; it does not undo Discord objects or restore member data.

## Future bots

Gate works without any active integration. Register companion bots by numeric user ID and either support or holder scope. Registration is inactive and changes no permissions. Activation requires admin review and grants scoped channel access only. Base permissions and role order remain admin-controlled.

An additional explicit handoff transfers responsibility for Ticket/Open/Closed or Holder Verification. No holder or ticket workflow is implemented here. The later bot must use the coordination protocol and recorded resource IDs. See COORDINATION.md.

## Operations

Service: `ripcars-gate`. Installation root: `/opt/ripcars-gate`. Persistent member data: `/var/lib/ripcars-gate/gate.sqlite3`. Shared coordination: `/var/lib/ripcars-bots/coordination.sqlite3`. Credentials: `/etc/ripcars-gate.env`.

The service runs as `ripcarsgate`, with systemd restart, readiness notification, a 90-second watchdog, daily SQLite API backups, and seven retained backups per database. In-Discord error alerts are rate-limited. Recent error records survive restart in the bounded audit table. Backups are on this VPS; no off-site storage is configured.

## Validation status

All 79 tests passed in the separately configured Python environment with real discord.py 2.6.4 and SQLite. No tests were skipped. New checks cover mirrored leases, atomic handoff, foreign ownership protection and separate private/shared paths. Four-process suite tests are recorded separately in SUITE_TEST_RESULTS.txt. See TEST_RESULTS.txt for the current execution boundaries.

The suite covers policies, actual bot startup, persistent Discord UI, a complete simulated admin/member entry session, CAPTCHA and role grants, notification role toggles, duplicate-free publishing, daily text submissions, failed-publish cooldown recovery, protected manual changes, shared coordination locks, stale settings, and backup integrity. Discord API calls and transport failures are mocked. This is not a private Discord server or a live gateway session.

Live Discord and VPS deployment have not been tested from this environment. The installer reruns the full suite after installing the pinned runtime, before switching the active release. Use ACCEPTANCE.md to verify your server's actual role hierarchy, channel permissions, and service before opening it.

Run full checks: `bash run_tests.sh`. Dependency-free diagnostics: `bash run_tests.sh --offline` (runtime tests skip if discord.py is missing).

Build new English packages with `python3 scripts/build_release.py /tmp/ripcars-gate-release-output`. The output directory must be outside this checkout and must not contain archives with the same version.
