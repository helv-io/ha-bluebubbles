# BlueBubbles

Home Assistant custom integration that sends and receives iMessage, RCS, SMS, and MMS via a [BlueBubbles](https://bluebubbles.app) server.

## Installation

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=helv-io&repository=ha-bluebubbles&category=Integration)

After adding the repository, search for BlueBubbles in HACS > Integrations, install it, then restart Home Assistant.

Or add the custom repository by hand:

1. Open HACS > Integrations.
2. Three dots > Custom repositories.
3. Add `https://github.com/helv-io/ha-bluebubbles` (category: Integration).
4. Search for BlueBubbles and install.
5. Restart Home Assistant.

Without HACS, copy `custom_components/bluebubbles/` from a [release][releases] into your Home Assistant config directory and restart.

## Setup

BlueBubbles server install is covered on the [BlueBubbles website][bluebubbles-website].

1. Settings > Devices & Services > Add Integration > BlueBubbles.
2. Enter:
   - **Host**: BlueBubbles server URL (`http://192.168.1.100:1234` or `https://your-domain.com`)
   - **Password**: the password set on the BlueBubbles server
   - **SSL** (optional, default off): leave off for a self-signed certificate
3. Submit. The integration connects, reads server info, and names the entry from the detected iMessage account.

The first send may show a macOS permission prompt on the machine running BlueBubbles. Accept it or sending will fail. See the [BlueBubbles docs][bluebubbles-docs].

Private API on the BlueBubbles server is required to send to more than one address. The integration reads that flag on setup and on Home Assistant restart.

Inbound webhooks are off until you enable them under **Configure**. Send-only setups do not need to change.

## send_message

`bluebubbles.send_message` sends iMessage, RCS, SMS, or MMS depending on the recipients.

Provide exactly one of `addresses` or `chat_guid`.

- **addresses**: phone numbers or emails. Separate multiple with commas or semicolons (Private API required for groups).
- **chat_guid**: GUID of an existing BlueBubbles chat, such as `trigger.chat_guid` from an inbound message.
- **message**: text to send. Optional when `attachment` or `media_url` is set.
- **attachment**: absolute path to a local file (for example `/config/www/snapshot.jpg`). The path must be allowed by [`allowlist_external_dirs`](https://www.home-assistant.io/docs/configuration/basic/#allowlist_external_dirs).
- **media_url**: URL of a file to download and attach. Used when `attachment` is not set.

```yaml
service: bluebubbles.send_message
data:
  addresses: "+15551234567, user@example.com"
  message: "Hello from Home Assistant!"
```

```yaml
service: bluebubbles.send_message
data:
  chat_guid: "{{ trigger.chat_guid }}"
  message: "Front door motion"
  attachment: "/config/www/snapshot.jpg"
```

## Inbound messages

1. Settings > Devices & Services > BlueBubbles > Configure.
2. Enable inbound message webhooks.
3. Leave auto-register on if the Mac can reach this Home Assistant URL (same LAN is enough).
4. Save. The form shows the webhook path (`/api/webhook/<id>`).

BlueBubbles must POST `new-message` events to that URL. Server 1.0.0+ is required. If auto-register fails, add the webhook in BlueBubbles Server > API & Webhooks (events: `new-message`).

Triggers (search **BlueBubbles** when adding an automation trigger, or use the BlueBubbles device):

| Trigger | When it fires |
|---|---|
| Message received | Any inbound message that passes filters |
| Phrase received | Message text matches a phrase (`contains`, `exact`, or `regex`) |

Trigger templates: `trigger.text`, `trigger.sender`, `trigger.sender_name`, `trigger.chat_guid`, `trigger.chat_identifier`, `trigger.message_guid`, `trigger.attachments`, `trigger.timestamp`, `trigger.service`, and `trigger.matched_phrase` on phrase triggers.

`event.<name>_message` updates with the same attributes.

Configure filters:

- **Allowed senders**: comma-separated phones or emails. Empty means all.
- **Include from me**: also fire on messages sent from the BlueBubbles Mac.

Triggers stay listed when inbound is off. They do not fire until inbound is enabled and BlueBubbles is posting `new-message` events.

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

```yaml
automation:
  - alias: Text Send Me The Bill
    trigger:
      - platform: bluebubbles.phrase_received
        options:
          phrase: "Send Me The Bill"
          match_type: contains
    action:
      - service: script.send_latest_bill
```

## Troubleshooting

- **Connection / send errors**: check host URL and password. Home Assistant logs include the redacted BlueBubbles response.
- **Permissions**: if sends fail, accept the macOS permission prompt on the BlueBubbles host.
- **Attachment path blocked**: add the directory to `allowlist_external_dirs` and restart Home Assistant.
- **Group send fails**: enable Private API on the BlueBubbles server.
- **SSL**: if HTTPS fails, toggle the SSL option.
- **Inbound not firing**: inbound enabled under Configure, BlueBubbles has a `new-message` webhook pointing at Home Assistant, and (if local-only) the Mac is on the same network. Check Home Assistant logs for `bluebubbles`.

Other issues: [issue tracker][issue-tracker].

## License

MIT. See [LICENSE][license].

[releases]: https://github.com/helv-io/ha-bluebubbles/releases
[bluebubbles-website]: https://bluebubbles.app
[bluebubbles-docs]: https://docs.bluebubbles.app
[issue-tracker]: https://github.com/helv-io/ha-bluebubbles/issues
[license]: https://github.com/helv-io/ha-bluebubbles/blob/main/LICENSE
