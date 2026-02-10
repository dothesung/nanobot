---
name: sys-stat
description: Monitor system resources (CPU, Memory, Disk, Network) and running processes. Use when asked about system health, resource usage, or "slow computer".
---

# System Statistics (sys-stat)

This skill provides real-time system monitoring capabilities using Python's `psutil`.

## Usage

When the user asks for system status, resource usage, or performance metrics, execute the included script:

```bash
python3 nanobot/skills/sys-stat/scripts/sys_stat.py
```

The script outputs JSON data containing:
- **CPU**: Usage percentage per core and overall load.
- **Memory**: Total, available, used, and percentage.
- **Disk**: Usage for all mounted partitions.
- **Network**: Bytes sent/received.
- **Processes**: Top 5 processes by CPU and Memory usage.

## Response Guidelines

- Summarize key metrics (CPU Load, RAM Usage, Disk Space).
- Highlight any anomalies (e.g., CPU > 90%, RAM > 90%, Disk > 90%).
- List top resource-consuming processes if load is high.
- Use emojis for readability (e.g., 🖥️ CPU, 🧠 RAM, 💾 Disk).
