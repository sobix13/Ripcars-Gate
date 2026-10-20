# Quiet launch: Gate 1.1.0

Open `/gate panel`. The first page shows Entry and CAPTCHA, Features on / off, Messages, Health, and More settings. All existing advanced tools remain under More settings.

## CAPTCHA-only entry

Open Features on / off and turn Questions off. A member completes CAPTCHA and receives the existing Ripper role. CAPTCHA expiry, member locks, Discord permissions and role hierarchy still apply. Existing questions and answers are retained. Turning Questions back on restores the original questionnaire.

Optional notification claims, gCARS submissions, channel filters and automatic repair have separate switches. Disabled features stop their checks and actions. Public panels close their controls when the corresponding feature is off. Existing custom messages are retained for reactivation.

## Private and archived channels

Move and hide channels manually in Discord. Gate preserves manual changes; it does not restore an archived channel's permissions automatically. Entry activation checks the Ripper role and verification channel, rather than requiring every optional template channel. Each enabled optional feature still needs its own access. Public publishing skips channels the bot cannot view or publish in.

The monitor detects protected resource changes using cached Discord objects. Automatic provisioning runs once per settings revision, not every minute. Failed changes require review; they are not retried continuously.

No member data, roles, channels or saved configuration is removed by this update.
