# Boot Persistence with launchd (macOS)

Create a launchd plist to start the watchdog automatically on login.

## Template

Save to `~/Library/LaunchAgents/com.claude-remote-sessions.watchdog.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.claude-remote-sessions.watchdog</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:$HOME/.local/bin</string>
        <key>HOME</key>
        <string>$HOME</string>
    </dict>
    <key>ProgramArguments</key>
    <array>
        <string>$PROJECT_DIR/scripts/discord-watchdog.sh</string>
        <string>--daemon</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>StandardOutPath</key>
    <string>$HOME/.claude/discord-sessions/watchdog-launchd.log</string>
    <key>StandardErrorPath</key>
    <string>$HOME/.claude/discord-sessions/watchdog-launchd.log</string>
</dict>
</plist>
```

Replace `$HOME` and `$PROJECT_DIR` with actual paths. Then:

```bash
launchctl load ~/Library/LaunchAgents/com.claude-remote-sessions.watchdog.plist
```

## Important

The `PATH` must include directories for `tmux`, `claude`, `python3`, and `curl`.
Check with `which tmux claude python3 curl` and add those directories.

## Linux (systemd)

```ini
[Unit]
Description=Claude Remote Sessions Watchdog
After=network.target

[Service]
ExecStart=/path/to/scripts/discord-watchdog.sh
Restart=always
Environment=HOME=/home/youruser

[Install]
WantedBy=default.target
```

Save to `~/.config/systemd/user/discord-watchdog.service`, then:

```bash
systemctl --user enable discord-watchdog
systemctl --user start discord-watchdog
```
