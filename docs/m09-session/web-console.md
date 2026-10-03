# M09: Local Collection Web Console

**Code style requirement: Economical code, exceptional readability, and excellent abstraction design.**

Status: requirements aligned, implementation deferred (2026-10-04).
The operator approved documenting this feature only. The collection station
is not reliably equipped with a monitor. No web server or control behavior is
implemented by this plan.

## Scope and ownership

Provide a local collection page with task selection, explicit Start Collection
and End Session controls, and state-dependent HOME/start/stop-save/discard
buttons corresponding to the existing Space, a and q actions. Display only the
current task, state, episode, elapsed recording time, finalization outcome and
concise actionable faults. Reuse the existing session state machine and its
single motion owner; the browser must never invoke a robot SDK directly.
Keyboard operation remains available. Deduplicate events from both interfaces,
reject stale commands and disable actions that are invalid in the current state.
Opening a page or reconnecting must never initiate motion or resume collection.

## Browser ownership and safe exit

The operator explicitly rejected continuing collection after closing its page.
Closing the owning page or pressing End Session must request safe session exit:
revoke following and pending gripper targets first, request the existing stop,
confirm standstill through fresh feedback, then finalize the valid episode or
retain partial data if completeness or stopping cannot be established. Do not
return HOME automatically and do not resume after reconnection.

Browser unload notifications are best effort, not a safety guarantee. A bounded
server-side ownership heartbeat must detect a closed tab, crashed browser,
lost SSH tunnel or client failure. Its timeout and browser-background behavior
need alignment and validation before implementation. Loss of this heartbeat
must enter the same safe-exit path; it must not depend on video delivery or
successful disk finalization. A refresh also loses ownership unless an explicit,
bounded handover is designed and accepted later. Multiple viewing tabs cannot
silently acquire or transfer control authority.

## Same-source preview and resource budget

Reuse the three existing camera sources. Never open additional camera pipelines.
During recording, preview accepted frame groups; while idle, show recent camera
frames clearly marked as not recording. Proposed initial budget: RGB only,
320 x 240, up to 5 frames/s per camera, with frame age visible.
Preview encoding, copying and network traffic have nonzero cost. Isolate them
from control and recording, keep only the latest preview, drop preview work under
pressure, and never backpressure capture, matching or storage. No connected
viewer means no preview encoding. Final rates and CPU/memory limits depend on
station stress measurements. Preview is advisory and never substitutes for
recording verification or robot stop confirmation.

## Local and SSH launch

On a station with a graphical desktop, the launcher can open the local page.
On a headless station it must print the URL and remain usable from a remote
client. A Mac-side launcher should establish an SSH local-forward tunnel and
open the Mac browser; a remote shell alone cannot reliably open that browser.
Bind the service to loopback, protect the command channel with a session token
and origin checks, and expose remote access through SSH rather than a public
unauthenticated control endpoint. Exact launch syntax remains to be aligned.

## Implementation sequence and acceptance

1. Align browser ownership timeout, refresh behavior and launch syntax.
2. Add one command adapter and state publication around the existing owner.
3. Add bounded same-source preview and the local/SSH launch integration.
4. Validate synthetic/simulator lifecycle and failure cases before hardware use.

- M09-A01: browser and keyboard produce the same episode boundaries; duplicate
  clicks cannot queue future motion. NOT RUN.
- M09-A02: close/crash/disconnect during HOME, following or stopping revokes
  authority and confirms stop, or explicitly reports unconfirmed stop. NOT RUN.
- M09-A03: headless and SSH operation, no reconnect restart, persistent capture
  resources across episodes and bounded preview load. NOT RUN.
- M09-A04: close during preparation/finalization, discard, recorder failure and
  valid-versus-partial outcomes remain truthful and do not delay stop. NOT RUN.
- M13: compare recording/control timing with preview off/on, stalled viewers and
  background tabs; accept no preview-induced gate regression. NOT RUN.

Real hardware motion requires separate explicit operator authorization. No
software or hardware acceptance is claimed by this requirements document.
