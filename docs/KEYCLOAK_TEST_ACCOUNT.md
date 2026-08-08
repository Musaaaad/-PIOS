# Creating a sign-in account in the `pios` realm

## Why sign-in fails with "Invalid username or password"

`deploy/keycloak/pios-realm.json` defines the realm, the nine role codes and the
`pios-portal` client. It defines **no users** — the file has no `users` key, and
no user seed exists anywhere in this repository.

So the `pios` realm starts empty. Every username tried against it is rejected,
and Keycloak's `Invalid username or password.` is the **correct** answer, not a
defect.

`admin` in particular does not exist there. The nearest thing is `KEYCLOAK_ADMIN`
(`pios-admin` in `render.yaml`), which is the **master** realm bootstrap
administrator. That account administers Keycloak itself; it is not a member of
the `pios` realm and cannot sign in to `pios-portal`.

## Why no credential is committed here

A password in git is a password published to everyone who can read the
repository, and realm import would then recreate it on every deploy. The realm
file stays credential-free by design; accounts are created once, by an operator,
in the admin console.

## Creating the account (manual, ~2 minutes)

Run by whoever holds the Keycloak admin password. Nothing in this repository
changes.

1. Open `https://<keycloak-host>/admin/` and sign in as `pios-admin`. The
   password is the Render-generated `KEYCLOAK_ADMIN_PASSWORD` — dashboard →
   `pios-keycloak` → Environment.
2. Switch the realm selector (top left) from **master** to **pios**. Getting
   this wrong creates the user in the wrong realm, and sign-in still fails.
3. **Users** → **Add user**
   - Username: `pilot.lead`
   - Email verified: **On** (otherwise a Verify Email required action blocks sign-in)
   - Create
4. **Credentials** tab → **Set password**
   - Set a password
   - **Temporary: Off** — with Temporary on, Keycloak forces an Update Password
     screen mid-flow and the redirect back to the app never completes
   - Save
5. **Details** tab → **Required user actions**: must be **empty**. Any entry
   (Verify Email, Update Password, Configure OTP) interrupts the redirect.
6. **Role mapping** tab → **Assign role** → filter by realm roles → assign at
   least one of the nine PIOS codes, e.g. `AccreditationLead`.
   The frontend signs in without a role, but the backend refuses every request
   from a token with no mapped role — deny by default.

## Verifying

1. Open the frontend and press **الدخول عبر الهوية المؤسسية**.
2. Sign in as `pilot.lead`.
3. The dashboard should appear with the role visible in the user chip.

If it fails, the browser console reports the stage without exposing anything
sensitive — `[pios-auth] CALLBACK_RECEIVED STATE_MISMATCH` and similar, or
`window.PIOS_AUTH.lastStage()`. That distinguishes a credential problem
(Keycloak rejects, the app is never reached) from a callback or token-exchange
problem (the app is reached and reports the stage).

## Role reference

`SystemAdmin`, `AccreditationLead`, `PharmacyDirector`, `MedicationSafety`,
`EvidenceCollector`, `EvidenceReviewer`, `CAPAOwner`, `CAPAVerifier`,
`ReadOnlyAuditor`.

These are exact codes — `require_roles(...)` compares them literally, and the
realm role name must match with no spaces.
