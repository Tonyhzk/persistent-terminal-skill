# Changelog

All notable changes to this project will be documented in this file.

**English** | [中文](CHANGELOG_CN.md)

---

## [1.1.0] - 2026-02-11

### Added
- **send command** - Send raw text to sessions, useful for passwords and interactive input
- **JSON config reading** - send command supports `--config` + `--key` to read text from JSON files, bypassing bash special character issues
- **Background mode** - create command supports `--background` flag for silent session creation

### Improved
- **Session management** - Optimized session state persistence using filesystem storage
- **Cross-platform compatibility** - Improved Windows subprocess execution mode

---

## [1.0.0] - 2026-02-11

### Initial Release

- **Persistent terminal sessions** - Maintain the same terminal session across multiple Claude Code conversation turns
- **Cross-platform support** - macOS/Linux via tmux, Windows via subprocess
- **Session operations** - Support for create, attach, exec, read, list, close, close-all commands
- **Foreground attach** - Opens system terminal window by default with live output
- **JSON output** - All commands return structured JSON format
- **Symlink tool** - setup_claude_dir.py for sharing configuration across projects