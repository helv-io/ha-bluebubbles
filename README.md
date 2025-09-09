# BlueBubbles Integration for Home Assistant

This integration allows you to send messages (iMessage/RCS/SMS/MMS) from Home Assistant using a BlueBubbles server. It connects to your BlueBubbles instance and exposes a service for sending messages.

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

## Services

The integration provides a single service for sending messages.

### send_message

Sends a message via BlueBubbles (iMessage/RCS/SMS/MMS depending on recipients).

- **addresses**: The address(es) to send to—phone numbers or emails, separated by commas or semicolons for groups (requires Private API enabled on your server). Required.
- **message**: The message to send. Required.

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

You can also call this service from the Developer Tools > Services page for testing.

## Troubleshooting

- **Connection Errors**: Double-check your host URL and password. Ensure the BlueBubbles server is running and accessible from your Home Assistant instance.
- **Permission Issues**: If messages aren't sending, verify permissions on your macOS BlueBubbles app as noted in the setup section.
- **Group Send Failures**: If sending to multiple addresses fails, ensure Private API is enabled on your BlueBubbles server (check server settings). The integration detects this automatically on setup and restarts.
- **SSL Problems**: If using HTTPS, try toggling the SSL option.
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