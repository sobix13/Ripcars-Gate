# Live acceptance before opening the server

These checks require the installed bot and a normal test account. Local tests do not validate real Discord permission hierarchy or your gateway settings.

1. Enable Server Members Intent and Message Content Intent for the Gate application. Invite only this bot. Use the Administrator permission for initial creation of the Admin/Team roles and per-channel setup. Put the bot's role above the roles it creates and assigns.
2. Run `/gate panel` → Server setup → Preview → Apply. Review setup-result.txt. Resolve every FAILED, BLOCKED, CONFLICT, MANUAL, or REVIEW entry. Repeating setup must not duplicate roles or channels.
3. Publish panels. Run `/gate health`. Fix all blockers. Activate entry.
4. Before verification, the test account sees only Rules, Verification, FAQ, and Official Links and reads their history. It cannot send messages or use thread replies to bypass read-only access.
5. Pass CAPTCHA without answering a question. Finish must reject the request and no Rippers role should be given.
6. Answer one question and finish. Rippers appears. General, community, support entry, Notifications, and Proposals are visible with history. Owners Chat, Holder Verification, ticket categories, and operations stay hidden.
7. Toggle all four notification roles twice. Each is added and removed. No claim role gives management permissions or bypasses initial verification.
8. General accepts text, image, link, and reactions. Read-only channels reject messages and thread replies. Show Off removes URL messages and non-image uploads while Gate is online.
9. Submit plain text to gCARS. The second submission is blocked until the cooldown. Links and mentions are rejected. Direct posting is denied. Restart Gate and confirm the cooldown persists.
10. Content's 2-hour native slowmode is set. Moderator reads the managed channels and moderates lower roles. OG alone opens Owners Chat and does not open Holder Verification or private ticket categories.
11. Change a managed permission manually. Gate preserves it and shows a resource review item. Keep current pins it. Restore template needs a separate confirmation.
12. Create an unrelated channel or role. Gate leaves it unchanged. Give an external bot a member-specific channel overwrite, then apply a Gate template change; the foreign overwrite must remain.
13. Delete one managed test channel. Gate reports it as missing and does not recreate it automatically. Explicitly bind a replacement ID and apply the reviewed template.
14. Edit a welcome text and question from Discord. Republish panels. Two admin forms opened on the same revision must not silently overwrite each other's saves.
15. Restart the service. Verification, claim, and gCARS public buttons still work. A CAPTCHA or question panel interrupted by restart is resumed through My status / Continue or a fresh challenge.
16. Export answers as an admin. Regular members must be denied admin functions. Check a backup, journal, and Discord error reporting. Keep the server closed if full tests or live acceptance fail.

Holder Verification remains hidden and the Ticket message is a placeholder. They are intentionally inactive until their separate companion bots are deployed.
