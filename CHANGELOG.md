# 1.0.1 compatibility update

Same-message deletion races with a companion moderator no longer create false Unknown Message errors or duplicate member notices. Only discord.NotFound is ignored; permission failures remain observable. No entry, question, role, schema, or server-template behavior changed. All 52 local tests passed; live deployment acceptance remains pending.

## 1.0.0 installation candidate

Standalone Rip Cars member entry with mandatory CAPTCHA and at least one answer. Rippers is granted only after both requirements. Admin-edited English text, questions, branding, channels, role names, and access settings. Burgundy default theme.

Server provisioning with per-channel permission maps, read-history access, manually assigned OG, staff-only Holder Verification, optional notification roles, and empty ticket categories. gCARS uses strict 24-hour submissions; Content uses native two-hour slowmode.

Resource-ID registry, shared setup leases, protected external changes, explicit adoption and handoff, separate member data, inactive companion registration, Discord error reports, settings history, backups, watchdog, and isolated VPS installation.

No application review stage, ticket engine, holder engine, or full moderation engine. All 50 local tests passed with real discord.py and mocked Discord API boundaries. Live Discord acceptance and VPS service checks remain pending; the installer reruns the full suite on the VPS.

## English GitHub distribution

- All deployment and validation documentation is English.
- Complete source, tests, dependencies and English TAR/ZIP packages are included.
- The installer excludes Git metadata and release archives when run from a checkout.
- No member onboarding, moderation, ticket or database behavior changed.
- Added the reusable clean release builder at `scripts/build_release.py`.
