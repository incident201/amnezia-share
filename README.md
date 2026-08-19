# amnezia-share 0.2.3

Headless AWG2/AWG3/AWG3.1 client management with AmneziaVPN-compatible dynamic QR and native `.conf` export for an Amnezia VPS.

Targets the current official Amnezia layout:

- Docker container: `amnezia-awg2`
- AWG2/AWG3/AWG3.1 config: `/opt/amnezia/awg/awg0.conf`
- clients table: `/opt/amnezia/awg/clientsTable`
- multi-QR framing compatible with the official Amnezia client

## Install

```bash
sudo ./install.sh
amnezia-share doctor
```

## Endpoint auto-detection

`--host` is optional. The endpoint host is resolved in this order:

1. Explicit `--host`, if supplied.
2. A public IPv4 address assigned to the interface used by the host's `main` default route (or its explicit `src`).
3. `curl -4 https://ifconfig.me/ip`.
4. Interactive prompt if automatic detection fails.

`SSH_CONNECTION` is not used for endpoint or SSH-port detection.

Examples:

```bash
amnezia-share client phone
amnezia-share full
```

Override only when needed:

```bash
amnezia-share client phone --host vpn.example.com
amnezia-share full --host 203.0.113.10
```

## Client access

Creates a fresh AWG client peer, updates `clientsTable`, applies `awg syncconf`, and shows a dynamic QR understood by AmneziaVPN:

```bash
amnezia-share client phone
```

The positional name is the peer/device name written to `clientsTable` (`clientName`). The Amnezia connection name (`description`) defaults independently to `Amnezia VPS`:

```bash
# clientsTable clientName: Ipad13; Amnezia connection: Amnezia VPS
amnezia-share client Ipad13

# clientsTable clientName: Ipad13; Amnezia connection: VPS Netherlands
amnezia-share client Ipad13 --description "VPS Netherlands"
```

`--description` does not affect the saved client name, list output, re-share selectors, or removal selectors. Full Access uses `--description` with the same connection-name meaning.

Export the same kind of native AWG `.conf` that the official client can share:

```bash
amnezia-share client phone --conf
```

Bare `--conf` writes `./phone.conf` with mode `0600` and does not require `qrencode`. You can also choose a path:

```bash
amnezia-share client phone --conf /root/phone.conf
```

MTU defaults to `1280` for both QR profiles and native `.conf` exports. Override it when needed:

```bash
amnezia-share client phone --mtu 1420
amnezia-share client phone --mtu 1420 --conf
```

The accepted range matches Amnezia Client: `576–65535`. Invalid values are rejected before `awg0.conf` or `clientsTable` is changed. In QR profiles MTU is stored as the official `last_config.mtu` field; native exports additionally write `MTU = ...` in `[Interface]`. The `.conf` also has the real DNS values substituted and can be imported by the official Amnezia Client.

Current AWG3/AWG3.1 interface parameters, including `RandomTrailers` and `DisableCookies`, are read automatically from `/opt/amnezia/awg/awg0.conf` and copied unchanged into client QR profiles, native `.conf` exports, and Full Access profiles. No separate CLI flags are required.

List/remove/re-share clients created by the helper:

```bash
amnezia-share list
amnezia-share reshare phone
amnezia-share remove phone
```

## Full access

`full` does **not** require an existing SSH private key. It generates a dedicated Ed25519 key pair, adds the public key to the selected local user's `authorized_keys`, puts the private key only into the generated Full Access Amnezia config/QR, and then deletes the temporary private-key file.

```bash
amnezia-share full
```

When run as root, the SSH user defaults to `root`. Override if needed. SSH port defaults to 22 and is only changed explicitly (or with `AMNEZIA_SSH_PORT`):

```bash
amnezia-share full --ssh-user ubuntu --ssh-port 2222
```

Each generated Full Access key gets an ID such as `9fb13d6ee342` and an `authorized_keys` comment `amnezia-share-full:<ID>`.

List and revoke only keys created by this helper:

```bash
amnezia-share full-list
amnezia-share full-revoke 9fb13d6ee342
```

The private Full Access key is deliberately **not** saved under `/var/lib/amnezia-share`; only non-secret metadata and the public key are kept so it can later be revoked. To share Full Access again, generate a new one and revoke the old one if desired.

## State

Root mode uses:

```text
/var/lib/amnezia-share/
├── clients/       # helper-created AWG client profiles (0600, needed for re-share)
├── full-access/   # metadata/public keys only; no Full Access private keys
└── backups/       # recent awg0.conf + clientsTable backups
```

## Terminal QR

The official Amnezia GUI uses 850-byte chunks and one frame per second. The helper uses the same data format; `--chunk-size auto` chooses the largest compatible chunk whose QR is about 78% of the terminal width and height. This leaves a small outer padding and may produce more frames, but makes scanning over SSH more reliable. Dynamic redraws use the terminal's alternate screen so old frames do not accumulate.

If rendering is poor:

```bash
amnezia-share client phone --qr-type UTF8
```
