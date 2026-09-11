---
name: "speckit.keel.connect"
description: "Check whether the local Keel runtime is connected, and start it if not."
---

Run the skill's own script and do exactly what it says:

```bash
python3 .specify/extensions/keel/scripts/keel_connect_check.py
```

It prints one line of JSON with an `outcome` key. Read `SKILL.md` beside it for the reply that
belongs to each outcome, and follow that file rather than improvising: it is the source of truth
for what a user is told, and it is the same file in every place this skill is installed.

Two things it asks of you that are easy to get wrong, so they are repeated here:

- **Relay `user_code` and `verification_uri` verbatim.** Do not shorten, rewrite or rebuild the
  URL. The Keel that issued it is the only thing that knows where its own approval screen is.
- **Never show the raw JSON**, and end your reply with one clause naming the `environment` the
  script reported -- which Keel this is.

To stop the runtime again, the same directory holds `scripts/keel_disconnect.py`, and `SKILL.md`
carries its six outcomes and their replies.
