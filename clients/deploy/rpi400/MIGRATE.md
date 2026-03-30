# Migrating RPi 400 from note-assistant → OmegaAgent

## What changes

| | Old (`note-assistant`) | New (`rpi400_assistant.py`) |
|---|---|---|
| AI runs on | RPi 400 (LangChain + Anthropic) | PN64 server |
| API keys needed | Yes (`.env` with Anthropic key) | No |
| Dependencies | langchain, anthropic, pyaudio, rich | `httpx` only |
| Vault access | Direct read/write | PN64 writes; Obsidian syncs |
| Reminder service | `reminder_service.py` or `--local-scheduler` | APScheduler on PN64 (automatic) |
| Voice/TTS | Local calls to GPU server | Proxied through PN64 |

**Keep Obsidian running** — the PN64 writes to the vault, Obsidian on the RPi syncs it.

---

## Step-by-step

### 1. Stop the old assistant

```bash
# Kill the old tmux session
tmux kill-session -t note-assistant 2>/dev/null

# If running as a systemd service:
sudo systemctl stop note-assistant.service
sudo systemctl disable note-assistant.service
```

### 2. Clone OmegaAgent

```bash
cd ~/Projects
git clone git@github.com:JaeminBBQ/OmegaAgent.git
```

### 3. Install the one dependency

```bash
pip3 install httpx
```

No venv needed — `httpx` is the only dependency for the RPi client.

### 4. Test manually

```bash
cd ~/Projects/OmegaAgent/clients
python3 rpi400_assistant.py
```

You should see:
```
╔════════════════════════════════════════════╗
║       OmegaAgent — RPi 400 Assistant      ║
...
```

Try `/tasks`, `/weather`, `/note list my tasks` to verify the PN64 connection.

### 5. Make the startup script executable

```bash
chmod +x ~/Projects/OmegaAgent/clients/deploy/rpi400/start_omega.sh
```

### 6. Swap the autostart desktop entry

```bash
# Remove old autostart
rm ~/.config/autostart/note-assistant-terminal.desktop

# Install new autostart
cp ~/Projects/OmegaAgent/clients/deploy/rpi400/omega-assistant-terminal.desktop \
   ~/.config/autostart/
```

### 7. (Optional) Install as systemd service instead

If you prefer headless mode over the desktop terminal:

```bash
sudo cp ~/Projects/OmegaAgent/clients/deploy/rpi400/omega-assistant.service \
        /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable omega-assistant.service
sudo systemctl start omega-assistant.service
```

### 8. Reboot and verify

```bash
sudo reboot
```

After reboot:
- Obsidian should open as before (unchanged)
- A terminal with `OmegaAgent` should appear on top
- Or if using systemd: `sudo journalctl -u omega-assistant.service -f`

Attach to tmux: `tmux attach -t omega`

---

## Cleanup (optional)

Once you've confirmed everything works:

```bash
# Remove old note-assistant autostart
rm -f ~/.config/autostart/note-assistant-terminal.desktop

# Remove old systemd service if installed
sudo systemctl disable note-assistant.service 2>/dev/null
sudo rm -f /etc/systemd/system/note-assistant.service
sudo systemctl daemon-reload

# Optionally archive the old project
mv ~/Projects/note-assistant ~/Projects/note-assistant.bak
```

---

## Commands available

```
/note <msg>          — talk to the note agent (conversational, uses tools)
/task <desc>         — quick-add a task
/tasks               — list pending tasks
/remind <msg> <time> — set a reminder (e.g. /remind Call dentist 3pm)
/reminders           — list upcoming reminders
/worklog <msg>       — add a work log entry
/capture <msg>       — quick daily note
/weather             — get Reno weather
/status              — check server health
/voice               — toggle TTS on/off
/quit                — exit
```

Or just type a question for Haiku (freeform chat).

---

## Troubleshooting

**"Connection refused" or can't reach PN64:**
- Verify PN64 is running: `curl http://172.16.0.200:8080/status`
- Check the RPi is on the same network

**tmux session won't start:**
- Check the script path: `cat ~/.config/autostart/omega-assistant-terminal.desktop`
- Run manually: `bash ~/Projects/OmegaAgent/clients/deploy/rpi400/start_omega.sh`

**Obsidian not showing new notes:**
- The vault is at `OBSIDIAN_VAULT_PATH` on the PN64 — make sure Obsidian on the RPi is pointed at the synced copy
- Check Obsidian Sync or whatever sync method you use is still active
