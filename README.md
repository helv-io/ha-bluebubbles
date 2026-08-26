# BlueBubbles Integration for Home Assistant

Send and receive iMessage/RCS/SMS/MMS from Home Assistant via a [BlueBubbles](https://bluebubbles.app) server.

## Architecture

- **Outbound**: `bluebubbles.send_message` talks to the BlueBubbles REST API (`/api/v1/chat/new`, `/api/v1/message/attachment`) through a shared `aiohttp` session (`async_get_clientsession`).
- **Inbound** (optional): Home Assistant registers a webhook (`/api/webhook/<id>`). BlueBubbles POSTs `new-message` events to it (auto-registered via `/api/v1/webhook` when enabled, or manually in the BlueBubbles UI).
- **Automations**: Integration triggers (`bluebubbles.message_received` / `bluebubbles.phrase_received`) and device triggers on the BlueBubbles device, all backed by the `bluebubbles_message_received` event. An `event.bluebubbles_message` entity also fires for Developer Tools / state-style triggers.

Existing installs that only send messages keep working with no reconfigure — inbound is opt-in under **Configure**.

## Upgrading to 0.6.0

0.6.0 is additive (no re-add required). After updating via HACS and reloading/restarting:

1. Send-only setups need no changes.
2. Triggers are discoverable by name: **Settings → Automations → Add trigger → search “BlueBubbles”**.
3. Or use **Device → BlueBubbles → Message received / Phrase received**.
4. To receive messages, open **Configure**, enable inbound webhooks, and save (a stable webhook id is created for you). Triggers stay visible even when inbound is off; they simply will not fire until inbound is enabled.

## Installation

### HACS (Recommended)

#### Option 1: Using My Button

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=helv-io&repository=ha-bluebubbles&category=Integration)

After adding the repository, search for "BlueBubbles" in HACS > Integrations and install it. Then, restart Home Assistant.

#### Option 2: Manual

1. Open HACS in Home Assistant.
2. Go to "Integrations".
3. Click the three dots in the top right and select "Custom repositories".
4. Add `https://github.com/helv-io/ha-bluebubbles` as a repository (category: Integration).
5. Search for "BlueBubbles" and install it.
6. Restart Home Assistant.

### Manual Installation

1. Download the latest release from the [releases page][releases].
2. Extract the contents to `custom_components/bluebubbles/` in your Home Assistant configuration directory.
3. Restart Home Assistant.

## How to Setup

This integration uses Home Assistant's configuration flow for setup. BlueBubbles server setup is outside the scope of this integration. Head over to the [BlueBubbles website][bluebubbles-website] for details on getting your server running.

1. In Home Assistant, go to Settings > Devices & Services.
2. Click "Add Integration" and search for "BlueBubbles".
3. You'll be prompted for the following:
   - **Host**: The URL of your BlueBubbles server (e.g., `http://192.168.1.100:1234` or `https://your-domain.com`).
   - **Password**: The password set in your BlueBubbles server.
   - **SSL** (optional, default: false): Enable if your server uses HTTPS with a self-signed certificate.
4. Submit the form. The integration will attempt to connect, fetch server details (including your iMessage account for naming), and verify.
5. If successful, the integration will be added with a title based on your detected iMessage account (e.g., "user@example.com").

**Important Note**: After initial setup, you may need to send a test message through the service. On the macOS machine running the BlueBubbles server app, a permission prompt might appear. Click to accept and grant access for message sending to work properly. Refer to the [BlueBubbles documentation][bluebubbles-docs] for more on permissions.

The integration automatically detects if Private API is enabled on your server and updates this on Home Assistant restarts. Private API is required for sending to multiple addresses (group messages); without it, only single-address sends are supported.

## Inbound messages & triggers

Inbound messaging is **opt-in** so existing send-only setups are unchanged. Jump to [Example automations](#example-automations) for copy-paste YAML.

1. Open **Settings → Devices & Services → BlueBubbles → Configure**.
2. Enable **Enable inbound message webhooks**.
3. Leave **Auto-register webhook with BlueBubbles server** on if Home Assistant has a URL the Mac can reach (same LAN is fine, e.g. `http://homeassistant.local:8123`).
4. Save. The options form shows the webhook path (for example `/api/webhook/<id>`). Saving Configure always persists a stable `webhook_id` (no ephemeral webhook for normal UX).

### Finding triggers in the UI

BlueBubbles does **not** appear as a top-level “trigger type” in older menus the way sun/time do on every screen. Use one of these paths:

1. **Recommended:** **Settings → Automations & Scenes → Create automation → Add trigger → search “BlueBubbles”** → choose **Message received** or **Phrase received**.
2. **Device path:** **Add trigger → Device → select your BlueBubbles device → Message received / Phrase received**.

Triggers are registered even when inbound is disabled; they will not fire until inbound webhooks are enabled and BlueBubbles is posting `new-message` events.

### Network notes

- BlueBubbles must be able to **POST** to your Home Assistant webhook URL.
- On a typical LAN, `http://<ha-host>:8123/api/webhook/<id>` works. Prefer **local only** (default) so the webhook rejects non-local callers.
- If auto-register fails (no HA URL, older BlueBubbles, etc.), add the webhook manually in **BlueBubbles Server → API & Webhooks → Add Webhook**:
  - URL: `http(s)://<home-assistant>/api/webhook/<id>`
  - Events: `new-message`
- BlueBubbles server **1.0.0+** is required for webhooks.

### Trigger types

| Trigger | When it fires |
|---|---|
| **Message received** | Any inbound message (after filters) |
| **Phrase received** | Message text matches a phrase (`contains`, `exact`, or `regex`) |

Trigger data available in templates includes: `trigger.text`, `trigger.sender`, `trigger.sender_name`, `trigger.chat_guid`, `trigger.chat_identifier`, `trigger.message_guid`, `trigger.attachments`, `trigger.timestamp`, `trigger.service`, and for phrase triggers `trigger.matched_phrase`.

The integration also creates **`event.<name>_message`** (translation: Message). It fires on inbound messages with the same attributes, so you can inspect the latest message in Developer Tools → States, or use a generic event-entity trigger.

Optional Configure filters:

- **Allowed senders** — comma-separated phones/emails; empty means all
- **Include from me** — also fire on messages sent from the BlueBubbles Mac

### Example automations

Any inbound message → notify (integration trigger):

```yaml
automation:
  - alias: iMessage received
    trigger:
      - platform: bluebubbles.message_received
    action:
      - service: notify.persistent_notification
        data:
          title: "iMessage from {{ trigger.sender }}"
          message: "{{ trigger.text }}"
```

Phrase match → run a script:

```yaml
automation:
  - alias: Text "Send Me The Bill"
    trigger:
      - platform: bluebubbles.phrase_received
        options:
          phrase: "Send Me The Bill"
          match_type: contains
    action:
      - service: script.send_latest_bill
```

Device trigger form (same events):

```yaml
automation:
  - alias: iMessage received (device)
    trigger:
      - platform: device
        domain: bluebubbles
        device_id: YOUR_BLUEBUBBLES_DEVICE_ID
        type: message_received
    action:
      - service: notify.persistent_notification
        data:
          title: "iMessage from {{ trigger.sender }}"
          message: "{{ trigger.text }}"
```

You can also listen for the raw bus event:

```yaml
trigger:
  - platform: event
    event_type: bluebubbles_message_received
```

## Services

### send_message

Sends a message via BlueBubbles (iMessage/RCS/SMS/MMS depending on recipients).

- **addresses**: The address(es) to send to—phone numbers or emails, separated by commas or semicolons for groups (requires Private API enabled on your server). Provide exactly one of `addresses` or `chat_guid`.
- **chat_guid**: The GUID of an existing BlueBubbles chat, such as the `trigger.chat_guid` value from an inbound message. Provide exactly one of `chat_guid` or `addresses`.
- **message**: The message to send. Optional when `attachment` or `media_url` is provided.
- **attachment**: Absolute path to a local file to attach (for example a camera snapshot under `/config/www/`). The path must be allowed via [`allowlist_external_dirs`](https://www.home-assistant.io/docs/configuration/basic/#allowlist_external_dirs). Optional.
- **media_url**: URL of an image/file to download and attach. Used when `attachment` is not set. Optional.

Example automation in YAML:

```yaml
automation:
  - alias: Send Test Message
    trigger:
      - platform: time
        at: "12:00:00"
    action:
      - service: bluebubbles.send_message
        data:
          addresses: "+15551234567, user@example.com"
          message: "Hello from Home Assistant!"
```

#### Sending an image

1. Ensure the file path is under an allowed directory, for example:

```yaml
# configuration.yaml
homeassistant:
  allowlist_external_dirs:
    - /config/www
```

2. Call the service with an `attachment` path (and optional caption in `message`):

```yaml
service: bluebubbles.send_message
data:
  addresses: "+15551234567"
  message: "Front door motion"
  attachment: "/config/www/snapshot.jpg"
```

Or attach a remote/local HTTP image with `media_url`:

```yaml
service: bluebubbles.send_message
data:
  addresses: "+15551234567"
  message: "Front door motion"
  media_url: "https://example.com/snapshot.jpg"
```

You can also call this service from the Developer Tools > Services page for testing.

#### Sending to an existing chat

Use the chat GUID exposed by an inbound message to reply to that exact conversation,
including an existing group chat. Sending by chat GUID does not require the Private API:

```yaml
service: bluebubbles.send_message
data:
  chat_guid: "any;+;bd802086b5494bb6a197b0c10625f9e9"
  message: "Reply from Home Assistant"
```

In an automation triggered by an inbound BlueBubbles message, it can be templated:

```yaml
action:
  - service: bluebubbles.send_message
    data:
      chat_guid: "{{ trigger.chat_guid }}"
      message: "Thanks, I received your message."
```

## Breaking changes

**None.** Config entries, `send_message` fields, option keys for existing setups, and translations for current outbound use remain compatible. Inbound messaging is additive and disabled until you enable it in Configure.

## Troubleshooting

- **Connection / Send Errors**: The service surfaces BlueBubbles API error messages in Home Assistant (instead of a generic "Unknown error"). Double-check your host URL and password, and review the Home Assistant log for the redacted response body.
- **Permission Issues**: If messages aren't sending, verify permissions on your macOS BlueBubbles app as noted in the setup section.
- **Attachment Path Blocked**: If sending an image fails with an allowlist error, add the directory to `allowlist_external_dirs` and restart Home Assistant.
- **Group Send Failures**: If sending to multiple addresses fails, ensure Private API is enabled on your BlueBubbles server (check server settings). The integration detects this automatically on setup and restarts.
- **SSL Problems**: If using HTTPS, try toggling the SSL option.
- **Can't find BlueBubbles triggers**: Update to **0.6.0** via HACS and reload. Then use **Automations → Add trigger → search BlueBubbles**, or **Device → BlueBubbles → Message received**. Device triggers are not listed under a separate “BlueBubbles” category outside the device picker.
- **Inbound not firing**: Confirm inbound is enabled under Configure, BlueBubbles has a `new-message` webhook pointing at Home Assistant, and (if using local-only) the Mac is on the same network. Check logs for `bluebubbles` webhook registration lines. Triggers can still be selected when inbound is off; they only fire after inbound is enabled.
- For other issues, check the Home Assistant logs (search for "bluebubbles") or open an [issue][issue-tracker].

## Contributing

Contributions are welcome! Feel free to submit pull requests or report bugs via the [issue tracker][issue-tracker].

## License

This integration is licensed under the MIT License. See the [LICENSE][license] file for details.

[releases]: https://github.com/helv-io/ha-bluebubbles/releases
[bluebubbles-website]: https://bluebubbles.app
[bluebubbles-docs]: https://docs.bluebubbles.app
[issue-tracker]: https://github.com/helv-io/ha-bluebubbles/issues
[license]: https://github.com/helv-io/ha-bluebubbles/blob/main/LICENSE

## Star History
Thank you for your support and feedback!

[![Star History Chart](https://api.star-history.com/svg?repos=helv-io/ha-bluebubbles&type=Date)](https://www.star-history.com/#helv-io/ha-bluebubbles&Date)
