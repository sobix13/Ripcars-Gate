# Companion coordination protocol, version 1

No companion process is launched by Gate. This document is the contract to implement in the later combined support/moderation bot and the later holder bot.

## Storage and identity

Use the shared coordination SQLite path configured in COORDINATION_PATH. On this VPS it is `/var/lib/ripcars-bots/coordination.sqlite3`. The member-profile database and token file are private to Gate. The coordination database's profile tables are empty; companion bots must not store personal member responses there.

Resource keys are `(guild_id, logical_key)`, such as `channel:general`, `channel:open_tickets`, and `role:rippers`. Object IDs, not names, establish identity. Different guilds are independent. A name collision is an adoption decision, not evidence of ownership.

`resources` holds object_id, kind, owner, baseline, desired, and state. Gate's owner string is `ripcars-gate`; handed-off resources use `bot:<numeric_user_id>`. Only active resources owned by the current bot may be reconciled. Manual, pinned, missing, partial, and external states are protected.

Baseline and desired overwrite maps list the permission fields owned by that controller. Preserve unlisted fields and every unrelated role/member overwrite. Never replace the complete channel overwrite dictionary on an existing channel.

## Mutations

Before any setup, adoption, repair, or handoff, acquire the guild's `server-setup` lease in the shared database. Use BEGIN IMMEDIATE, a random token, and an expiry. Renew during a long operation. Release only if the token matches. This coordinates participating bots only; Discord admins and third-party bots do not honor this lock.

Re-read the object and baseline before writing. If a managed field no longer matches baseline, preserve it and mark manual. If the object is missing, mark missing instead of automatically recreating it. Adopt or replace an ID only after explicit admin review.

Gate monitors active records once a minute. It does not police unknown channels or roles. Audit logs may help identify an external actor; they are not the authority for resource ownership.

Gate's server-setup flow and monitoring use the shared lease. The later bots must use it too. Discord does not provide an atomic compare-and-swap for these channel edits, so a manual edit during the final API write window remains a possible race. The next scan reports divergence. A claim that arbitrary third-party bots can never conflict would be inaccurate.

## Access activation and handoff

Register a numeric bot user ID in the admin center. Registration is inactive and does not auto-trust newly joined bots. Support access is limited to Ticket, Open, Closed, and Gate Log. Holder access is limited to Holder Verification. Activation changes those member-specific channel overwrites only. It does not edit the bot's managed integration role, grant Administrator, or implement its workflow.

Gate currently initializes Ticket, Open, and Closed. Transfer their responsibility explicitly after the companion is configured. The support bot may then create per-user tickets, allow the ticket author in their own open ticket, preserve staff access, and remove author access after closure. Gate must never repair these ticket objects.

The holder bot receives Holder Verification only after its own rollout. OG remains manually assigned until a separately approved holder policy is implemented. No wallet provider, asset address, token threshold, or ownership check is assumed here.

The basic no-link/image filter and daily posting currently belong to Gate. Before moving them into the combined moderation/support bot, disable or transfer the Gate controller for the relevant resources and implement equivalent checks in the new bot. Never run two enforcement controllers for the same rule.

## Compatibility tests for later releases

Test shared lease contention, foreign overwrite preservation, manual edits, deleted resources, same-name adoption, responsibility handoff, bot absence, restart during setup, and running Gate alone. Use unique slash command groups and button custom IDs per application.
