# Escaping Google Photos: a field report

*How we tried to build a seamless Google Photos → Immich migration, and how every
door we opened led to a smaller door.*

---

At Freepod we host private, dedicated pods of open-source apps — photos, files,
chat, passwords — for people who want their digital life back. For photos that
means [Immich](https://immich.app), which is a genuinely excellent, self-hosted
Google Photos replacement. But an empty Immich is a hard sell. The photos are
*in* Google Photos: ten, fifteen years of them, hundreds of gigabytes, sometimes
terabytes, lovingly sorted into albums. If switching means abandoning that
archive — or wrestling it out by hand — most people will quite rationally stay
put.

So we set out to build the obvious thing: a migration flow where a non-technical
user clicks a few buttons, waits a few days, and finds their entire photo
library — albums and all — waiting in their own Immich instance. Photos in
Google, photos out of Google. How hard could it be?

Reader, let us count the ways.

## Door one: the Photos API (bricked up in 2025)

The clean solution would be an API. The user grants us read access to their
Google Photos library via OAuth, we enumerate everything, download the
originals, recreate the albums. One consent screen, zero manual steps. This is
how you'd design it if the platform *wanted* to let you.

That door closed on March 31, 2025. Google removed the
`photoslibrary.readonly` scope — along with `photoslibrary.sharing` and the
broad `photoslibrary` scope — from the Photos Library API. The endpoints still
exist, but they can now only see media items *your own app created*. An app can
no longer list, search, or download a user's existing photo library. At all.

The designated replacement is the Photos **Picker** API, which lets a user
hand-select photos in a Google-hosted dialog and pass them to your app. It is
built for "attach three photos to a post," not "give me all 80,000." There is
no bulk selection to speak of, and — fatally for migration — no album
structure comes back with the picks.

So the API route isn't merely awkward; it is *architecturally impossible*.
Google's official position is that bulk export is what Google Takeout is for.
Hold that thought.

## Door two: Takeout, the export that resists automation

Google Takeout does produce a genuinely complete export: full-resolution
originals plus JSON sidecars carrying timestamps, GPS data, favorites, and
album membership. The community tool [immich-go](https://github.com/simulot/immich-go) can ingest a Takeout archive
and reconstruct the whole structure inside Immich — albums included. The *data*
path exists and it's good.

The *control* path is another matter. Takeout is a browser-only flow: sign in,
deselect forty-odd Google products, select Photos, choose an archive format and
chunk size, choose a destination, click go, and then wait — hours to days for
large libraries — for Google to assemble the archive. There is no Takeout API.
There is no CLI. There is nothing to script. For a service like ours, the
export step is a wall of manual clicking, and it's manual *by design*.

Our first architecture leaned into that: ship a small desktop app bundling a
browser and Playwright, let the user sign in, then drive the Takeout UI
programmatically — deselect everything, select Photos, configure, submit. The
user watches the robot click; everyone is happy.

Google is not happy. Google's sign-in page actively detects automated
browsers — Playwright, Puppeteer, Selenium, headless or not — and rejects them
with *"This browser or app may not be secure."* This detection is deliberate,
effective, and has grown stricter over the years. The stealth-plugin
countermeasures the scraping community once relied on went unmaintained around 2023.
And repeatedly poking a real user's Google account with automation risks
security lockouts on the very account whose photos we're trying to rescue. You
can automate *after* a manual sign-in with somewhat less hostility, but you're
then screen-scraping a UI that Google can rearrange any Tuesday, in a flow that
handles the user's crown-jewel credentials. We noped out.

We also examined the fully client-side variant — do everything on the user's
machine, no server involved — and discarded it on physics. A terabyte-scale
library means days of Takeout generation, then a huge download to a laptop that
must stay open, then a *re-upload* through consumer broadband whose uplink is a
fraction of its downlink. Any crash, sleep, disk-full, or Wi-Fi hiccup along
the way and a non-technical user is stranded halfway through a multi-day
process they don't understand. Migration belongs on servers: fast symmetric
pipes, resumable, unattended.

## Door three: Takeout → Drive → us (or: a short taxonomy of scopes)

Takeout can deposit its archives directly into the user's Google Drive (also
Dropbox, OneDrive, or Box — remember that, it matters later). That suggested a
neat pipeline: user runs Takeout once, pointing it at Drive; our servers watch
the Drive folder, pull the archives as they land, and feed them to immich-go.
The user's laptop exits the story after five minutes of clicking.

All we need is permission to read one folder of the user's Drive. Enter the
Google Drive scope taxonomy, where the fun really begins.

Drive scopes come in tiers. The broad read scopes — `drive`, `drive.readonly` —
are **restricted** scopes. Requesting them triggers, beyond ordinary app
verification, an annual third-party security assessment under the CASA
framework: an external auditor, a Letter of Validation, a bill that starts
around $500 and climbs with your user count, every single year, forever. For a
small privacy-focused service, that's a permanent tax — paid, with some irony,
for the privilege of moving data *out* of Google.

Then there's `drive.file`, the scope Google actively steers developers toward.
It's classified non-sensitive: no security audit, only basic verification. The
catch: it grants access solely to files your app *created* or files the user
*explicitly hands you* through the Google Picker. Per-file. Per-item. It is the
"safe" scope precisely because it can't roam.

But there was a glimmer of hope in the fine print: the Picker lets users pick
*folders*, and picking a folder extends some kind of grant to your app. If
"some kind of grant" included reading the folder's contents, we'd have
everything: user picks their Takeout folder once, our server (holding an
offline refresh token) polls it, downloads the archives, done. No restricted
scope, no audit, no fee.

Does a folder grant include the folder's *pre-existing children*? Here the
documentation simply goes silent. The scope's description speaks of "files."
Community forums leaned pessimistic but unofficial. There was exactly one way
to find out: build it and ask the API.

## The 401 that ate three days

We built the spike — OAuth code flow with offline access, refresh token stored
server-side, Picker in the browser for the folder selection. The OAuth dance
worked on the first try. The refresh token minted fresh access tokens
beautifully. And the Picker dialog answered every attempt with an HTTP 401 and
a blank stare.

What followed was a diagnostic odyssey we'll compress for your benefit, though
it refused to be compressed for ours:

- **Third-party cookies.** The Picker runs in an iframe served from
  `docs.google.com`. Google's own engineers have explained that it *requires*
  the Google session cookie in that iframe — it deliberately does not trust the
  OAuth token alone, because the dialog shows files your app doesn't have
  access to yet. Third-party cookie? In this economy? Chrome is actively
  deprecating those. We allowed them. We added exceptions for Google's domains.
  Still 401.
- **The cookies were even being *sent*.** We could see the session cookies on
  the network request. But the Picker's gate page checks cookies via JavaScript
  inside the iframe, and a partitioned third-party frame can receive cookies on
  the wire while its scripts see an empty jar. Two different mechanisms,
  identical symptom. Still 401.
- **HTTP versus HTTPS.** Our dev setup ran on plain `http://localhost`, and the
  session cookies in question are `__Secure-`-prefixed, bound to secure
  contexts. Plausible! We minted local certificates, moved dev to HTTPS,
  untangled the mixed-content and CORS fallout that changing schemes drags in,
  and eventually deployed the whole spike to a real domain with a real
  certificate. Still 401.
- **Our code.** We threw away our hand-rolled Picker bootstrap and adopted
  Google's official web component, on the theory that we'd wired the arcane
  gapi internals wrong. (We had, in fact, wired one thing wrong — a custom
  element that never registered — which produced a *different*, more
  entertaining failure: a picker that didn't open at all.) Fixed that.
  Still 401.
- **The credentials triangle.** Token, OAuth client, API key, project numbers,
  API enablement, key restrictions — audited, cross-checked, screenshot-
  verified. All correct. Still 401.

The breakthrough came from the experiment we should have run on day one:
loading *Google's own hosted Picker demo* — their code, their credentials,
their domain — in the same browser. It failed identically. The problem was
never our project, our origin, our scheme, or our code.

It was **Privacy Badger**. The EFF's tracker-blocking extension, quietly doing
exactly its job in a signed-in browser, was severing the Picker iframe's
session. Disable it, and everything worked — our spike included — on the first
try.

We'd love to be annoyed at the extension, but the joke lands on us twice over.
First: a browser extension was the one variable we never put on the suspect
list, and a clean-profile control test would have exposed it in five minutes.
Second, and more strategically: Freepod's entire audience is privacy-conscious
people. *Our* users, of all users, run Privacy Badger and its cousins. Any
onboarding flow built on a third-party Google iframe will fail for exactly the
people we're trying to onboard — silently, with a misleading "please sign in"
message that took two engineers three days to see through.

## The verdict: a folder is not its files

With the Picker finally rendering, we could run the actual experiment. The user
picks their Takeout folder; our server, using only the stored refresh token,
asks three questions: Can you read the folder? Can you list its children? Can
you download one?

The result, against a real Takeout folder containing two files:

```
folder GET .......... 200  (the folder object itself: visible)
children list ....... 200  (the response: an empty array)
verdict ............. no recursive access
```

Note the shape of that failure. Not a 403. Not an error of any kind. Under
`drive.file`, the Drive API acts as a lens: every call succeeds, and the
results are silently intersected with your grant. The folder was granted; its
pre-existing children were not; so listing them returns a truthful, useless,
*perfectly successful* empty list. A production system built on the wrong
assumption wouldn't crash — it would poll an "empty" folder forever, which is
a far crueler failure mode than a loud denial.

So the answer to the undocumented question is **no**. Picking a folder grants
the folder object — enough to create new files inside it, not enough to read
what's already there. The one Google Drive scope that doesn't cost an annual
security audit is, by construction, incapable of bulk egress. The scopes that
are capable of it are the ones with the price tag.

## The scorecard

Every approach, and the wall it hit:

| Approach | Wall |
|---|---|
| Photos Library API, read the library | Scopes removed in 2025; app-created media only |
| Photos Picker API | Hand-picking only; no albums; unusable at library scale |
| Automate Takeout with Playwright | Bot detection at sign-in; account-lockout risk; brittle scraping |
| Fully client-side desktop migration | Days-long, fragile, asymmetric-uplink physics on consumer hardware |
| Takeout → Drive, read with `drive.readonly` | Restricted scope → annual paid CASA audit |
| Takeout → Drive, read with `drive.file` + folder pick | Folder grant excludes pre-existing children (verified empirically) |
| Anything involving the Picker iframe | Third-party-cookie dependence; silently broken by privacy extensions |

What survives:

1. **Per-file selection.** `drive.file` grants do apply to files the user
   explicitly multi-selects. With Takeout configured for 50 GB chunks, a
   terabyte is ~20 files. But the user must return days later — after Takeout
   finishes — and select every archive without missing one, in an iframe their
   privacy extension may be quietly strangling.
2. **Share the folder with a service account.** The oldest sharing mechanism
   in Drive: the user shares their Takeout folder with an email address —
   ours — using the native Drive sharing dialog they've used a hundred times.
   A service account reading folders explicitly shared *to it* uses its own
   credentials: no user OAuth, no consent screens, no scopes requested, no
   audits, no Picker, no iframes, no cookies, nothing for an extension to
   block. Full recursive read. As of this writing it's our lead candidate,
   pending validation.
3. **Route around Google Drive entirely.** Takeout also exports directly to
   Dropbox, OneDrive, and Box — whose OAuth models will happily grant a folder
   of read access without an annual audit. Reliability of Google's push into
   third-party clouds is reportedly spottier, and it demands the user have an
   account with free space elsewhere, but it converts the problem from "Google
   permission maze" to "ordinary cloud API."

That the *most promising* design is "please share a folder with our robot's
email address" — the mechanism Drive launched with over a decade ago — after
all of the above, is the kind of punchline you couldn't write on purpose.

## On the economics of doors

Step back from any single wall and look at the maze. Every barrier we hit has
an individually reasonable justification. Photos API lockdown? Protects users
from data-harvesting apps. Bot detection at sign-in? Protects accounts from
credential stuffing. Third-party cookie requirements in the Picker? Prevents
token-replay against files you haven't been granted. CASA audits for broad
Drive scopes? Raises the bar for apps touching everything. Silent filtering
under `drive.file`? Principle of least astonishment, arguably. Each door,
examined alone, is defensible security engineering.

But notice the direction every door swings. Uploading your photos to Google
is frictionless from every device you own; the ingestion APIs are superb.
Getting them *out* programmatically was possible for years — until 2025, when
it wasn't. The officially blessed export can't be scripted, resists
automation at the sign-in gate, and dribbles into destinations that a
third-party service either can't read (without an annual fee) or can't read
*completely* (without undocumented gaps you discover by experiment). Google's
revenue doesn't come from your subscription so much as from your presence —
your data, your attention, your gravitational pull on everyone who shares
albums with you. Egress isn't a feature with a bug; friction *is* the feature.

Takeout itself deserves recognition as a masterpiece of regulatory
positioning. It exists, it's complete, it's free — nobody can say Google
doesn't offer data portability; data-protection rules in force in the EU and
elsewhere effectively require that it exists. And it is precisely as usable as
compliance demands and not one click more: browser-only, unscriptable,
slow-drip, delivered as a pile of zip chunks whose reassembly is the user's
problem. Portability *the right* can be demonstrated in a hearing;
portability *the experience* would cost Google users. Guess which one shipped.

We don't think there's a villain in a bunker cackling over the `drive.file`
spec. It's simpler than that: when a company's incentives all point toward
retention, a thousand small, individually-reasonable security decisions will
just happen to compose into a wall, and nobody is ever assigned the ticket to
cut a gate in it. The wall is emergent. It is also, from where we stand,
extremely real.

## What we learned

- **Run the control experiment first.** Loading the vendor's own demo on day
  one would have saved three days of debugging our own blameless code. When a
  black box rejects you, first establish whether it accepts *anyone* in your
  environment.
- **Browser extensions are part of your users' environment** — especially
  when your product self-selects for privacy tooling. Test your onboarding in
  a browser wearing the same armor your users wear.
- **Silence is worse than failure.** An API that returns a successful empty
  list instead of a permission error will ship a bug into production that a
  403 would have stopped in development. Where docs are silent, test against
  known ground truth.
- **Read the incentives, not just the documentation.** The docs told us what
  each scope does. Only the incentive structure explained why the pieces
  refuse to compose into a working migration — and predicted, correctly,
  where we'd get stuck next.

The photos, for the record, are still coming out. It just won't be through the
front door.

*Next up: teaching a service account to accept a folder invitation.*
