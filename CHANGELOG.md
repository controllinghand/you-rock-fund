## [1.2.0] - May 2026
### Added
- scripts/yrvi-restart.sh: re-injects Keychain secrets before docker restart, fixing individual container restarts
- Watchdog auto-restarts ib_gateway after 30 min down outside market hours (never during 9:30–4:00 PM ET)
- auto_restart_gateway setting with dashboard toggle (default true)
### Changed
- Watchdog alerts distinguish auto-restart attempted vs manual intervention required
### Notes
- Drops beta label — first full stable release with live trading resilience features

## [0.1.0-beta] - April 2026
### Added
- Complete wheel strategy automation
- IBC auto-login
- React dashboard with dark/light mode
- Discord integration
- Live IBKR portfolio view
- Settings management
- Paper/Live trading toggle

## [1.1.0-beta] - April 2026
### Added
- macOS Keychain secrets management (replaces manual docker/secrets/ file creation)
- setup_docker.sh --paper / --live mode flags (required, replaces bare invocation)
- Password double-entry confirmation with character count on first run
- Ephemeral secret files — written at launch, deleted after containers start
- Secret rotation via Keychain Access.app (delete entry, re-run script)
- README: Hardware Requirements table, Security section, You Rock Club onboarding note
### Changed
- Steps 5 & 6 idempotent — login item and Desktop app skip if already installed
- Hardware tier policy: Mac Mini required for live trading, Windows scoped to paper only
- Versioning policy documented in README Version History

## [1.0.0-beta] - April 2026
### Added
- Docker containerization (replaces launchd)
- Cross-platform: Mac Intel/ARM + Windows
- Secrets management via macOS Keychain (ephemeral docker/secrets/ files)
- Auto-start via Docker login plist
- nginx serving React dashboard
- Socket-based health checks
- Scheduler heartbeat monitoring
### Changed
- setup_docker.sh replaces setup_ibc.sh
- startup.sh now checks Docker containers
