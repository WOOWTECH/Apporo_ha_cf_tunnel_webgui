# AGENTS.md

Rules for every agent and person who changes this repository: Apporo CF Tunnel
Web, a Home Assistant add-on (folder `cloudflared/`, slug
`apporo_cf_tunnel_web`) forked from WOOWTECH's Woow Cloudflared 1.1.3. Its
platform link goes to Apporo Security Access on `https://www.apporo.ai`.

## Making a change

1. **Change `main` through a pull request.** Push a branch, open a PR, and
   merge it when the Build workflow is green.
2. **CI must pass.** `.github/workflows/build.yaml` runs the Web GUI, add-on
   and frontend tests, the frontend build, and the add-on build for amd64 and
   aarch64. Run its test steps locally before you push (README.md,
   "Development", lists them), and fix a red check before merging.
3. **Publish by bumping the version.** In the same PR, raise `version` in
   `cloudflared/config.yaml` and add a top entry to `cloudflared/CHANGELOG.md`.
   After the merge, CI pushes
   `ghcr.io/woowtech/{arch}-addon-apporo-cf-tunnel-web:<version>`. A published
   version is never rebuilt, so a merge without a bump publishes nothing. When
   CI cannot ask GHCR whether the version exists, the build job fails rather
   than publish; re-run it once GHCR answers.
   Home Assistant offers the update as soon as `main` carries the new version,
   and installs fail until the image is pushed: merge a bump only with every
   check green.
4. **Keep every image package public.** The Supervisor pulls add-on images
   without credentials. The amd64 and aarch64 packages are public, and a public
   package cannot be made private again. GitHub can create a new package (an
   added architecture or image name) as private: open it under
   `https://github.com/users/WOOWTECH/packages`, choose Package settings >
   Change visibility > Public, and check that `docker pull` of its new tag
   works on a machine that is not logged in to ghcr.io.

## Keep fixed

Guard tests pin these; change a pin only together with a deliberate change to
what it guards.

- **The add-on identity** (`cloudflared/tests/test_addon_identity.py`): name,
  slug, image, repository and the options schema keys. Home Assistant keys an
  installed add-on by repository and slug, and users' saved options by the
  schema keys; changing either strands existing installs.
- **The platform contract** (`cloudflared/webgui/tests/test_branding.py`, with
  the fake platform in `test_paas.py`): the OAuth client id
  `woow-ha-smart-home`, the scopes, the device-code grant, and every `/api` and
  `/oauth2` path and payload key. The Apporo platform shares them with WOOW's
  platform, so the `woow` in them is the platform's, not branding.
  `test_branding.py` also pins the origin `https://www.apporo.ai`, the device
  label `Apporo CF Tunnel Web (HA add-on)` and English backend messages.
- **Apporo branding in the UI**
  (`cloudflared/webgui/frontend/src/__tests__/branding.spec.ts`): English text,
  the Apporo palette (gold `#8B6B24`) and the Apporo favicon.

When merging from upstream (README.md, "Merging from upstream"), keep the
Apporo side of every conflict; these tests catch WOOW names that slip back in.
