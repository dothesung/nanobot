#!/usr/bin/env python3
"""
System Resource Monitor for Nanobot.
Outputs JSON-formatted system metrics.
"""

import json
import psutil
import datetime
import os
import platform

def get_stats():
    stats = {}
    
    # OS Info
    stats['os'] = platform.system()
    stats['release'] = platform.release()
    stats['hostname'] = platform.node()
    stats['uptime'] = str(datetime.timedelta(seconds=int(psutil.boot_time())))
    
    # CPU
    stats['cpu'] = {
        'percent': psutil.cpu_percent(interval=1),
        'count': psutil.cpu_count(),
        'freq': psutil.cpu_freq().current if psutil.cpu_freq() else 0,
        'load_avg': [x / psutil.cpu_count() for x in psutil.getloadavg()] if hasattr(psutil, "getloadavg") else []
    }
    
    # Memory
    mem = psutil.virtual_memory()
    stats['ram'] = {
        'total_gb': round(mem.total / (1024**3), 2),
        'available_gb': round(mem.available / (1024**3), 2),
        'percent': mem.percent
    }
    
    # Disk
    stats['disk'] = []
    for part in psutil.disk_partitions():
        try:
            usage = psutil.disk_usage(part.mountpoint)
            stats['disk'].append({
                'device': part.device,
                'mountpoint': part.mountpoint,
                'total_gb': round(usage.total / (1024**3), 2),
                'used_gb': round(usage.used / (1024**3), 2),
                'percent': usage.percent
            })
        except PermissionError:
            continue
            
    # Network
    net = psutil.net_io_counters()
    stats['network'] = {
        'sent_mb': round(net.bytes_sent / (1024**2), 2),
        'recv_mb': round(net.bytes_recv / (1024**2), 2)
    }
    
    # Top Processes
    procs = []
    for p in psutil.process_iter(['pid', 'name', 'username', 'cpu_percent', 'memory_percent']):
        try:
            procs.append(p.info)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
            
    # Sort by CPU
    top_cpu = sorted(procs, key=lambda p: p['cpu_percent'], reverse=True)[:5]
    top_mem = sorted(procs, key=lambda p: p['memory_percent'], reverse=True)[:5]
    
    stats['top_processes_cpu'] = top_cpu
    stats['top_processes_mem'] = top_mem
    
    return stats

if __name__ == '__main__':
    try:
        data = get_stats()
        print(json.dumps(data, indent=2))
    except Exception as e:
        print(json.dumps({"error": str(e)}))
