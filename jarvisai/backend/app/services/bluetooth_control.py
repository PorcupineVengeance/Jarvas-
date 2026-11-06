"""Permissioned Bluetooth helpers for JARVIS Desktop (list / connect / disconnect)."""

from __future__ import annotations

import json
import platform
import re
import shutil
import subprocess
from typing import Any

from app.core.permissions import bluetooth_control_enabled


class BluetoothControlError(RuntimeError):
    pass


def _require_enabled() -> None:
    if not bluetooth_control_enabled():
        raise BluetoothControlError(
            "Bluetooth control is disabled. Enable it in Settings → Desktop permissions."
        )


def _run(cmd: list[str], *, timeout: float = 20.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _normalize_address(value: str) -> str:
    raw = re.sub(r"[^0-9A-Fa-f]", "", (value or "").strip())
    if len(raw) != 12:
        return (value or "").strip().upper()
    parts = [raw[i : i + 2] for i in range(0, 12, 2)]
    return ":".join(parts).upper()


def _mac_list_devices() -> list[dict[str, Any]]:
    try:
        proc = _run(["system_profiler", "SPBluetoothDataType", "-json"], timeout=25.0)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise BluetoothControlError("Could not read Bluetooth status on this Mac.") from exc
    if proc.returncode != 0:
        raise BluetoothControlError("Bluetooth status is unavailable.")
    try:
        payload = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise BluetoothControlError("Bluetooth status could not be parsed.") from exc

    devices: list[dict[str, Any]] = []
    blocks = payload.get("SPBluetoothDataType")
    if not isinstance(blocks, list):
        return devices

    def add_device(name: str, info: dict[str, Any], *, connected: bool | None = None) -> None:
        address = (
            info.get("device_address")
            or info.get("device_address_title")
            or info.get("address")
            or ""
        )
        state = connected
        if state is None:
            raw_state = str(info.get("device_connected") or info.get("connected") or "").lower()
            if raw_state in {"yes", "true", "connected", "1"}:
                state = True
            elif raw_state in {"no", "false", "disconnected", "0"}:
                state = False
        devices.append({
            "name": name,
            "address": _normalize_address(str(address)) if address else "",
            "connected": state,
            "type": info.get("device_minorType") or info.get("device_type") or info.get("device_productID") or None,
            "vendor": info.get("device_vendorID") or info.get("vendor_id") or None,
        })

    for block in blocks:
        if not isinstance(block, dict):
            continue
        # Newer macOS shapes: controller_properties + device_connected / device_not_connected maps
        for key, group_connected in (
            ("device_connected", True),
            ("device_not_connected", False),
            ("devices_list", None),
        ):
            group = block.get(key)
            if isinstance(group, dict):
                for name, info in group.items():
                    if isinstance(info, dict):
                        add_device(str(name), info, connected=group_connected)
            elif isinstance(group, list):
                for item in group:
                    if not isinstance(item, dict):
                        continue
                    # Current macOS: [{ "AirPods": { device_address: ... } }, ...]
                    nested_named = [
                        (str(name), info)
                        for name, info in item.items()
                        if isinstance(info, dict) and name not in {"_name", "name"}
                    ]
                    if nested_named:
                        for name, info in nested_named:
                            add_device(name, info, connected=group_connected)
                        continue
                    name = str(item.get("_name") or item.get("name") or "").strip()
                    if name:
                        add_device(name, item, connected=group_connected)
        # Older/alternate nested list under controller
        nested = block.get("_items")
        if isinstance(nested, list):
            for item in nested:
                if isinstance(item, dict) and item.get("_name"):
                    add_device(str(item["_name"]), item)

    # Deduplicate by address/name
    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in devices:
        key = (item.get("address") or item.get("name") or "").lower()
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def _windows_list_devices() -> list[dict[str, Any]]:
    script = (
        "Get-PnpDevice -Class Bluetooth -ErrorAction SilentlyContinue | "
        "Select-Object FriendlyName, Status, InstanceId | ConvertTo-Json -Compress"
    )
    try:
        proc = _run(
            ["powershell", "-NoProfile", "-Command", script],
            timeout=30.0,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise BluetoothControlError("Could not read Bluetooth devices on Windows.") from exc
    if proc.returncode != 0:
        raise BluetoothControlError("Bluetooth device listing failed on Windows.")
    raw = (proc.stdout or "").strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise BluetoothControlError("Windows Bluetooth list could not be parsed.") from exc
    rows = data if isinstance(data, list) else [data]
    devices: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("FriendlyName") or "").strip()
        if not name:
            continue
        status = str(row.get("Status") or "").lower()
        instance = str(row.get("InstanceId") or "")
        address_match = re.search(r"([0-9A-Fa-f]{12})$", instance.replace("&", ""))
        address = _normalize_address(address_match.group(1)) if address_match else ""
        devices.append({
            "name": name,
            "address": address,
            "connected": status == "ok",
            "status": row.get("Status"),
            "instance_id": instance or None,
            "type": None,
            "vendor": None,
        })
    return devices


def list_devices() -> dict[str, Any]:
    _require_enabled()
    system = platform.system()
    if system == "Darwin":
        devices = _mac_list_devices()
    elif system == "Windows":
        devices = _windows_list_devices()
    else:
        raise BluetoothControlError("Bluetooth control is currently supported on macOS and Windows.")
    return {
        "action": "bluetooth.list",
        "platform": system,
        "count": len(devices),
        "devices": devices,
        "note": "Only paired devices known to the OS are listed. Some accessories only fully respond in their vendor apps.",
    }


def _find_device(query: str) -> dict[str, Any]:
    needle = (query or "").strip().lower()
    if not needle:
        raise BluetoothControlError("Provide a device name or Bluetooth address.")
    listed = list_devices()["devices"]
    address_needle = _normalize_address(query).lower()
    exact: list[dict[str, Any]] = []
    partial: list[dict[str, Any]] = []
    for item in listed:
        name = str(item.get("name") or "").lower()
        address = str(item.get("address") or "").lower()
        if address and address == address_needle:
            exact.append(item)
        elif name == needle:
            exact.append(item)
        elif needle in name or (address and needle.replace(":", "") in address.replace(":", "")):
            partial.append(item)
    matches = exact or partial
    if not matches:
        raise BluetoothControlError(f"No paired Bluetooth device matched “{query.strip()}”.")
    if len(matches) > 1 and not exact:
        names = ", ".join(str(m.get("name")) for m in matches[:5])
        raise BluetoothControlError(f"Multiple devices matched. Be more specific: {names}")
    return matches[0]


def _mac_blueutil_available() -> str | None:
    return shutil.which("blueutil")


def _mac_connect_disconnect(address: str, *, connect: bool) -> dict[str, Any]:
    blueutil = _mac_blueutil_available()
    if not blueutil:
        raise BluetoothControlError(
            "Connecting/disconnecting needs the free `blueutil` tool on macOS. "
            "Install with: brew install blueutil — then try again. "
            "Listing paired devices still works without it."
        )
    flag = "--connect" if connect else "--disconnect"
    # blueutil accepts address with or without separators
    compact = address.replace(":", "").replace("-", "")
    try:
        proc = _run([blueutil, flag, compact], timeout=25.0)
    except subprocess.TimeoutExpired as exc:
        raise BluetoothControlError("Bluetooth command timed out.") from exc
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip() or "unknown error"
        raise BluetoothControlError(f"Bluetooth {'connect' if connect else 'disconnect'} failed: {detail}")
    return {
        "action": "bluetooth.connect" if connect else "bluetooth.disconnect",
        "address": address,
        "status": "ok",
        "helper": "blueutil",
    }


def _windows_connect_disconnect(device: dict[str, Any], *, connect: bool) -> dict[str, Any]:
    instance = device.get("instance_id")
    if not instance:
        raise BluetoothControlError("Windows could not identify that Bluetooth device instance.")
    cmd = "Enable-PnpDevice" if connect else "Disable-PnpDevice"
    # May require elevation for some devices.
    script = f"{cmd} -InstanceId '{str(instance).replace(chr(39), '')}' -Confirm:$false"
    try:
        proc = _run(["powershell", "-NoProfile", "-Command", script], timeout=30.0)
    except subprocess.TimeoutExpired as exc:
        raise BluetoothControlError("Bluetooth command timed out.") from exc
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip() or "Access denied or unsupported."
        raise BluetoothControlError(
            f"Windows could not {'connect' if connect else 'disconnect'} the device ({detail}). "
            "Some adapters need Administrator permission."
        )
    return {
        "action": "bluetooth.connect" if connect else "bluetooth.disconnect",
        "name": device.get("name"),
        "instance_id": instance,
        "status": "ok",
        "helper": "powershell-pnp",
    }


def connect_device(query: str) -> dict[str, Any]:
    _require_enabled()
    device = _find_device(query)
    system = platform.system()
    if system == "Darwin":
        address = str(device.get("address") or "")
        if not address:
            raise BluetoothControlError("That device has no Bluetooth address available for connect.")
        result = _mac_connect_disconnect(address, connect=True)
        result["name"] = device.get("name")
        return result
    if system == "Windows":
        return _windows_connect_disconnect(device, connect=True)
    raise BluetoothControlError("Bluetooth connect is currently supported on macOS and Windows.")


def disconnect_device(query: str) -> dict[str, Any]:
    _require_enabled()
    device = _find_device(query)
    system = platform.system()
    if system == "Darwin":
        address = str(device.get("address") or "")
        if not address:
            raise BluetoothControlError("That device has no Bluetooth address available for disconnect.")
        result = _mac_connect_disconnect(address, connect=False)
        result["name"] = device.get("name")
        return result
    if system == "Windows":
        return _windows_connect_disconnect(device, connect=False)
    raise BluetoothControlError("Bluetooth disconnect is currently supported on macOS and Windows.")
