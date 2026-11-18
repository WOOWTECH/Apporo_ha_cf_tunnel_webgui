# Apporo CF Tunnel Web

Connect an Apporo Security Access (Cloudflare Tunnel) to Home Assistant without
opening ports, with a Web GUI.

A Security Access is the tunnel service of the Apporo platform
([www.apporo.ai][apporo]). The platform creates the Cloudflare tunnel and its
public hostnames (routes), and can put a Cloudflare Access sign-in in front of
each route. This add-on runs the connector, `cloudflared`, inside Home
Assistant. It also works with your own Cloudflare account.

Apporo CF Tunnel Web is the Apporo fork of WOOWTECH's Woow Cloudflared add-on
1.1.3, which adds a Web GUI to [homeassistant-apps/app-cloudflared][upstream].
The tunnel and its options work as upstream documents them; see
[Configuration](#configuration).

## Web GUI

Open it with **Open Web UI** or **Apporo Tunnel** in the sidebar. It is served
through Ingress: no extra port, protected by your Home Assistant login.

- **Dashboard**: tunnel status (edge connections), add-on state, restart.
- **Apporo Link**: connect an Apporo Security Access (below).
- **Setup**: a local-managed tunnel in your own Cloudflare account. The
  Cloudflare authorization URL appears as a link instead of in the log.
- **Config**: every add-on option, saved through the Supervisor, so the
  Configuration tab shows the same values.
- **Logs**: the live add-on log, with filter and download.

With an empty configuration, the Web GUI keeps running with the tunnel stopped,
so the first setup can happen in the browser.

## Connect an Apporo Security Access

First create the Security Access on [www.apporo.ai][apporo]: a workspace, a
plan and at least one route. Plans, trials and payment are handled there; the
add-on never charges anything.

### Apporo Link (recommended)

1. On **Apporo Link**, choose **Get device code**. Open the device page
   (`https://www.apporo.ai/device`), sign in, enter the code and allow the
   connection. Your account must be an owner or admin of the workspace.
1. Choose the workspace, then the Security Access.
1. Review the routes. You can connect when the service is active, its
   subscription is valid, its tunnel exists, it is not bound to another device,
   and every route has a hostname and a service URL. A route with Access also
   needs Access seats, a login method (Email OTP or Google) and an allow rule
   that names specific emails or an email domain. A route without Access is
   public: anyone who knows the hostname reaches the service, so its own login
   must be on, and you confirm such routes before connecting. Fix problems on
   the portal (routes on the **Application** tab, protection on the **Access**
   tab), then choose **Check again**.
1. Choose **Connect and enable**. The add-on is bound on the platform as
   `Apporo CF Tunnel Web (HA add-on)`, the token is saved in `tunnel_token`, and
   the add-on restarts.

**Refresh connection status** and **Test public URLs** check the result. The
anonymous test shows how each hostname answers; it does not prove that a given
person can sign in. After a route's protection changes, the hostname answers
503 until the platform publishes the change, which needs a live connector.

While the link is active, the token cannot be changed on the Config page.
**Stop the local connection and release the binding** clears the token and the
local route options (`external_hostname`, `additional_hosts`,
`catch_all_service`, `nginx_proxy_manager`), restarts the add-on, and then
releases the binding on the platform. Hostnames, DNS records, Access settings
and the subscription stay on the portal until you delete them there.

### Tunnel token

On the portal, open the Security Access, then **Overview** > **Connect a
machine** > **Tunnel token**. Paste the token on the Config page and choose
**Save & Restart**, or set `tunnel_token` on the Configuration tab and restart
the add-on. The routes then come from the platform, and the local route options
are ignored. Run a token in one place at a time: with two connectors on one
token, Cloudflare may send visitors to either of them.

### Route targets

`cloudflared` runs on Home Assistant's internal network, so a route's service
URL names Home Assistant as `homeassistant`: `http://homeassistant:<port>`, with
the **Server port** shown under **Settings > System > Network > HTTP server**.
That is usually 80 on recent installations (the default under the Supervisor
since Home Assistant 2026.8) and 8123 on older ones. Point a route at another
add-on by the hostname on its Info page, or at a device by its address. A 502
means a wrong address or port, or a service that is down; a 400 from Home
Assistant means it does not trust the proxy yet (next section).

## Home Assistant configuration

Home Assistant answers 400 Bad Request to requests that come through a proxy it
does not trust. Trust the network that add-ons get their addresses from:

- In **Settings > System > Network > HTTP server**, under **Reverse proxy**,
  turn on **Trust X-Forwarded-For** and add `172.30.33.0/24` to **Trusted
  proxies**. Save, restart Home Assistant, and confirm the new HTTP server
  settings when Home Assistant asks. Since Home Assistant 2026.8 this page is
  the place for these settings: an `http:` block in `configuration.yaml` is
  imported once and ignored after that.
- In releases before 2026.8, which have no such page, add this to
  `configuration.yaml` instead and restart Home Assistant:

  ```yaml
  http:
    use_x_forwarded_for: true
    trusted_proxies:
      - 172.30.33.0/24
  ```

**On a non-standard installation (e.g. Proxmox), you might have to trust
another address. Check the Home Assistant log after a failed request to find
it.**

For `external_hostname`, the add-on points the tunnel at `homeassistant` on the
port from the HTTP server settings; before 2026.8, on the port from the
`http:` block of `configuration.yaml`. It uses `https` only when the `http:`
block in `configuration.yaml` sets `ssl_certificate` and `ssl_key`. The add-on
reads that block only from `configuration.yaml` itself, not from
[`!include`][homeassistant-config-splitting] files or
[packages][homeassistant-config-packages].

## Your own Cloudflare account

You need a domain that uses Cloudflare for DNS ([how-to][how-tos]; domains from
**Freenom** no longer work) with [WebSockets enabled][cloudflare-websockets].
Choose a local tunnel, managed by the add-on, or a remote tunnel, managed in
Cloudflare's dashboard ([learn more][addon-remote-or-local]).

### Local tunnel

1. Configure Home Assistant as described in
   [Home Assistant configuration](#home-assistant-configuration).
1. Set `external_hostname` to the hostname for remote access, for example
   `ha.example.com`. To expose only other services, leave it empty and set
   `additional_hosts`.
1. Start the add-on. This overwrites existing DNS records for those hostnames.
1. Open the Cloudflare authorization link, shown on the Setup page and in the
   log, and authorize your domain.
1. Open Home Assistant at the remote URL without a port, e.g.
   `https://ha.example.com/`.

The tunnel then appears in your Cloudflare Zero Trust dashboard.

### Remote tunnel

1. Configure Home Assistant as described in
   [Home Assistant configuration](#home-assistant-configuration).
1. Create a tunnel in the Cloudflare Zero Trust dashboard
   ([how-to][addon-remote-tunnel]).
1. Set `tunnel_token` to its [tunnel token][create-remote-managed-tunnel].
   All route options are then ignored.
1. Start the add-on and check the log.

Make any further route changes in the Cloudflare dashboard.

## Configuration

**Note**: _Restart the add-on after changing the configuration. The Web GUI's
**Save & Restart** does both._

The route options (`external_hostname`, `additional_hosts`, `tunnel_name`,
`catch_all_service`, `nginx_proxy_manager`) apply to a local tunnel only. With
`tunnel_token` set, they are ignored; `post_quantum`, `run_parameters` and
`log_level` apply to both.

Example configuration:

```yaml
external_hostname: ha.example.com
additional_hosts:
  - hostname: router.example.com
    service: http://192.168.1.1
  - hostname: website.example.com
    service: http://192.168.1.3:8080
```

**Note**: _This is just an example, don't copy and paste it! Create your own!_

### Option: `external_hostname`

The domain or subdomain on which you want to reach Home Assistant. Optional:
`additional_hosts` can be used instead to expose only other services.

```yaml
external_hostname: ha.example.com
```

### Option: `additional_hosts`

More hostnames routed through the tunnel, for example a NAS or a router. Like
`external_hostname`, their DNS records are created at Cloudflare. Add
`disableChunkedEncoding: true` to a host to turn off chunked transfer encoding,
which helps with WSGI servers such as Proxmox
([Cloudflare docs][disablechunkedencoding]).

```yaml
additional_hosts:
  - hostname: router.example.com
    service: http://192.168.1.1
  - hostname: diskstation.example.com
    service: https://192.168.1.2:5001
  - hostname: website.example.com
    service: http://192.168.1.3:8080
    disableChunkedEncoding: true
```

**Note 1**: _A hostname removed from the list is no longer served, but its DNS
record stays at Cloudflare. Delete it there yourself._

**Note 2**: _To remove the option completely, set it to an empty list:_

```yaml
additional_hosts: []
```

### Option: `tunnel_name`

The name of the tunnel the add-on creates, `homeassistant` by default. It must
be unique in your Cloudflare account.

```yaml
tunnel_name: myHomeAssistant
```

### Option: `catch_all_service`

A URL that receives requests for every hostname not defined in
`external_hostname` or `additional_hosts`, for example a reverse proxy. The
defined hostnames are still routed as configured. For the
[Nginx Proxy Manager][nginx_proxy_manager] add-on, use `nginx_proxy_manager`
instead.

```yaml
catch_all_service: http://192.168.1.100
```

Each extra hostname needs its own CNAME record at Cloudflare, pointing to your
`external_hostname` or to the tunnel's URL (the target of the
`external_hostname` CNAME). A
[wildcard record](https://blog.cloudflare.com/wildcard-proxy-for-everyone/)
(a CNAME named `*`) also works.

### Option: `nginx_proxy_manager`

Sends every request for an undefined hostname to the
[Nginx Proxy Manager][nginx_proxy_manager] add-on; `catch_all_service` is then
ignored. The defined hostnames are still routed as configured. The same CNAME
records as for `catch_all_service` are needed. Then set up your proxy hosts in
Nginx Proxy Manager.

```yaml
nginx_proxy_manager: true
```

### Option: `post_quantum`

Makes the tunnel use post-quantum cryptography.

**Note**: _This restricts the tunnel to the QUIC transport, which causes
problems for some users, and it never falls back to a connection without
post-quantum key exchange._

```yaml
post_quantum: true
```

### Option: `tunnel_token`

The token of a remote-managed tunnel: from the Apporo portal for a Security
Access, or from the Cloudflare dashboard. When set, all route options are
ignored. Home Assistant shows it masked. While an Apporo Link is active, the
link manages this option; release the binding on the Apporo Link page before
you change it.

### Option: `run_parameters`

Extra parameters for the cloudflared daemon, each as `--flag=value`. Allowed:

- `--edge-bind-address`
- `--edge-ip-version`
- `--grace-period`
- `--ha-connections`
- `--logfile`
- `--loglevel`
- `--pidfile`
- `--protocol`
- `--region`
- `--retries`
- `--tag`

See the [Cloudflare documentation][cloudflare-run_parameter] for what they do.

**Note**: _The add-on always sets `--no-autoupdate` and
`--metrics=127.0.0.1:36500`, plus `--origincert` and `--config` for a local
tunnel or `--token-file` for a remote one. You cannot override these, and the
add-on refuses to start with `--token`, `--token-file` or `--metrics` in this
list._

**Note**: _Paths can start with `/config`, the add-on's own configuration
folder._

```yaml
run_parameters:
  - "--region=us"
  - "--protocol=http2"
  - "--loglevel=debug"
```

### Option: `log_level`

How much the add-on logs. For the tunnel itself, use `--loglevel` in
`run_parameters`.

```yaml
log_level: debug
```

Possible values:

- `trace`: every detail, like all called internal functions.
- `debug`: detailed debug information.
- `info`: normal (usually) interesting events.
- `notice`: normal but significant events.
- `warning`: exceptional occurrences that are not errors.
- `error`: runtime errors that do not require immediate action.
- `fatal`: something went terribly wrong; the add-on becomes unusable.

Each level includes the more severe ones; `debug` also shows `info` messages.
The default, `info`, is the recommended setting unless you are troubleshooting.

## Disclaimer

Please make sure you comply with the
[Cloudflare Self-Serve Subscription Agreement][cloudflare-sssa] when using this
add-on.

## More help

- Apporo CF Tunnel Web on GitHub: [README and issues][repo]
- How-tos and troubleshooting for the tunnel core: the
  [upstream wiki][addon-wiki]

## Authors and license

The tunnel core is the work of [homeassistant-apps][github-org] (originally set
up by [Tobias Brenner][tobias]; see the [contributors][contributors]). The Web
GUI and the guided platform link are by [WOOWTECH][woowtech]. The Apporo fork is
by Apporo.

MIT License. Copyright (c) 2026 Unofficial Home Assistant Apps (Add-ons) and
(c) 2026 Apporo. The full text is in [LICENSE.md][license].

[apporo]: https://www.apporo.ai
[repo]: https://github.com/WOOWTECH/Apporo_ha_cf_tunnel_webgui
[license]: https://github.com/WOOWTECH/Apporo_ha_cf_tunnel_webgui/blob/main/LICENSE.md
[upstream]: https://github.com/homeassistant-apps/app-cloudflared
[woowtech]: https://github.com/WOOWTECH
[addon-remote-tunnel]: https://github.com/homeassistant-apps/app-cloudflared/wiki/How-tos#how-to-configure-remote-tunnels
[addon-remote-or-local]: https://github.com/homeassistant-apps/app-cloudflared/wiki/How-tos#local-vs-remote-managed-tunnels
[addon-wiki]: https://github.com/homeassistant-apps/app-cloudflared/wiki
[homeassistant-config-splitting]: https://www.home-assistant.io/docs/configuration/splitting_configuration/
[homeassistant-config-packages]: https://www.home-assistant.io/docs/configuration/packages/
[cloudflare-sssa]: https://www.cloudflare.com/en-gb/terms/
[cloudflare-run_parameter]: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/configure-tunnels/tunnel-run-parameters/
[cloudflare-websockets]: https://developers.cloudflare.com/network/websockets/
[contributors]: https://github.com/homeassistant-apps/app-cloudflared/graphs/contributors
[how-tos]: https://github.com/homeassistant-apps/app-cloudflared/wiki/How-tos
[nginx_proxy_manager]: https://github.com/hassio-addons/addon-nginx-proxy-manager
[tobias]: https://github.com/brenner-tobias
[disablechunkedencoding]: https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/configuration/configuration-file/ingress#disablechunkedencoding
[create-remote-managed-tunnel]: https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/tunnel-guide/#1-create-a-tunnel
[github-org]: https://github.com/homeassistant-apps
