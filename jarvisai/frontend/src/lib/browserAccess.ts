/** Browser-side device access for hosted web JARVIS (permissioned, opt-in). */

export type BrowserPermissionKey =
  | 'geolocation'
  | 'notifications'
  | 'clipboard'
  | 'battery'
  | 'share'
  | 'wake_lock'
  | 'files'
  | 'camera'
  | 'screen_capture'
  | 'vibrate'
  | 'downloads';

export type BrowserPermissions = Record<BrowserPermissionKey, boolean>;

const STORAGE_KEY = 'jarvis.browser_permissions_v2';

const DEFAULTS: BrowserPermissions = {
  geolocation: true,
  notifications: true,
  clipboard: true,
  battery: true,
  share: true,
  wake_lock: true,
  files: true,
  camera: true,
  screen_capture: true,
  vibrate: true,
  downloads: true,
};

let wakeLock: WakeLockSentinel | null = null;

export function getBrowserPermissions(): BrowserPermissions {
  try {
    const raw = localStorage.getItem(STORAGE_KEY) || localStorage.getItem('jarvis.browser_permissions_v1');
    if (!raw) return { ...DEFAULTS };
    const parsed = JSON.parse(raw) as Partial<BrowserPermissions>;
    return { ...DEFAULTS, ...parsed };
  } catch {
    return { ...DEFAULTS };
  }
}

export function setBrowserPermission(key: BrowserPermissionKey, enabled: boolean): BrowserPermissions {
  const next = { ...getBrowserPermissions(), [key]: enabled };
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  } catch { /* ignore quota */ }
  window.dispatchEvent(new CustomEvent('jarvis:browser-permissions', { detail: next }));
  return next;
}

export function setBrowserPermissions(next: BrowserPermissions): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  } catch { /* ignore */ }
  window.dispatchEvent(new CustomEvent('jarvis:browser-permissions', { detail: next }));
}

export function detectBrowserCapabilities() {
  const nav = typeof navigator !== 'undefined' ? navigator : undefined;
  return {
    geolocation: Boolean(nav?.geolocation),
    notifications: typeof Notification !== 'undefined',
    clipboard: Boolean(nav?.clipboard?.writeText),
    clipboard_read: Boolean(nav?.clipboard?.readText),
    battery: typeof (nav as Navigator & { getBattery?: () => Promise<unknown> })?.getBattery === 'function',
    share: typeof nav?.share === 'function',
    wake_lock: Boolean(nav?.wakeLock?.request),
    files: true,
    camera: Boolean(nav?.mediaDevices?.getUserMedia),
    screen_capture: Boolean(nav?.mediaDevices?.getDisplayMedia),
    vibrate: typeof nav?.vibrate === 'function',
    downloads: true,
    connection: Boolean((nav as Navigator & { connection?: unknown })?.connection),
    storage: Boolean(nav?.storage?.estimate),
  };
}

async function readGeo(): Promise<Record<string, unknown> | null> {
  if (!navigator.geolocation) return null;
  return new Promise((resolve) => {
    const timer = window.setTimeout(() => resolve(null), 6000);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        window.clearTimeout(timer);
        resolve({
          latitude: pos.coords.latitude,
          longitude: pos.coords.longitude,
          accuracy_m: pos.coords.accuracy,
          altitude: pos.coords.altitude,
          heading: pos.coords.heading,
          speed: pos.coords.speed,
          source: 'browser_geolocation',
        });
      },
      () => {
        window.clearTimeout(timer);
        resolve(null);
      },
      { enableHighAccuracy: true, timeout: 5500, maximumAge: 60_000 },
    );
  });
}

async function readBattery(): Promise<Record<string, unknown> | null> {
  const getBattery = (navigator as Navigator & { getBattery?: () => Promise<{
    level: number; charging: boolean; chargingTime: number; dischargingTime: number;
  }> }).getBattery;
  if (!getBattery) return null;
  try {
    const bat = await getBattery();
    return {
      level_percent: Math.round(bat.level * 100),
      charging: bat.charging,
      charging_time_sec: Number.isFinite(bat.chargingTime) ? bat.chargingTime : null,
      discharging_time_sec: Number.isFinite(bat.dischargingTime) ? bat.dischargingTime : null,
    };
  } catch {
    return null;
  }
}

function readConnection(): Record<string, unknown> | null {
  const connection = (navigator as Navigator & {
    connection?: { effectiveType?: string; downlink?: number; rtt?: number; saveData?: boolean };
  }).connection;
  if (!connection) return null;
  return {
    effective_type: connection.effectiveType ?? null,
    downlink_mbps: connection.downlink ?? null,
    rtt_ms: connection.rtt ?? null,
    save_data: Boolean(connection.saveData),
  };
}

async function readStorage(): Promise<Record<string, unknown> | null> {
  if (!navigator.storage?.estimate) return null;
  try {
    const est = await navigator.storage.estimate();
    const usage = est.usage ?? 0;
    const quota = est.quota ?? 0;
    return {
      usage_mb: Math.round((usage / (1024 * 1024)) * 100) / 100,
      quota_mb: Math.round((quota / (1024 * 1024)) * 100) / 100,
      usage_percent: quota ? Math.round((usage / quota) * 1000) / 10 : null,
    };
  } catch {
    return null;
  }
}

async function listMediaInputs(): Promise<Record<string, unknown> | null> {
  if (!navigator.mediaDevices?.enumerateDevices) return null;
  try {
    const devices = await navigator.mediaDevices.enumerateDevices();
    return {
      audio_inputs: devices.filter((d) => d.kind === 'audioinput').length,
      video_inputs: devices.filter((d) => d.kind === 'videoinput').length,
      audio_outputs: devices.filter((d) => d.kind === 'audiooutput').length,
    };
  } catch {
    return null;
  }
}

export async function gatherBrowserContext(options?: { message?: string }): Promise<Record<string, unknown>> {
  const prefs = getBrowserPermissions();
  const caps = detectBrowserCapabilities();
  const message = (options?.message || '').toLowerCase();
  const wantsClipboard = /\b(clipboard|paste|copied text|what(?:'s| is) on my clipboard)\b/.test(message);

  const context: Record<string, unknown> = {
    surface: 'web_browser',
    permissions: prefs,
    capabilities: caps,
    locale: navigator.language || null,
    languages: Array.from(navigator.languages || []).slice(0, 8),
    platform: navigator.platform || null,
    user_agent: navigator.userAgent.slice(0, 180),
    online: navigator.onLine,
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || null,
    timezone_offset_min: new Date().getTimezoneOffset(),
    screen: {
      width: window.screen?.width ?? null,
      height: window.screen?.height ?? null,
      avail_width: window.screen?.availWidth ?? null,
      avail_height: window.screen?.availHeight ?? null,
      pixel_ratio: window.devicePixelRatio || 1,
      viewport_width: window.innerWidth,
      viewport_height: window.innerHeight,
      orientation: window.screen?.orientation?.type ?? null,
      color_depth: window.screen?.colorDepth ?? null,
    },
    visibility: document.visibilityState,
    hardware_concurrency: navigator.hardwareConcurrency ?? null,
    device_memory_gb: (navigator as Navigator & { deviceMemory?: number }).deviceMemory ?? null,
    max_touch_points: navigator.maxTouchPoints ?? 0,
  };

  if (prefs.battery && caps.battery) context.battery = await readBattery();
  if (caps.connection) context.connection = readConnection();
  if (prefs.geolocation && caps.geolocation) context.geolocation = await readGeo();
  context.storage = await readStorage();
  context.media_devices = await listMediaInputs();

  if (prefs.clipboard && caps.clipboard_read && wantsClipboard) {
    try {
      const text = await navigator.clipboard.readText();
      context.clipboard_text = text.slice(0, 4000);
      context.clipboard_truncated = text.length > 4000;
    } catch {
      context.clipboard_error = 'Clipboard read was blocked by the browser. Ask the user to allow clipboard access.';
    }
  }
  if (prefs.notifications && caps.notifications) {
    context.notification_permission = Notification.permission;
  }

  return context;
}

export async function requestBrowserPermission(key: BrowserPermissionKey): Promise<{ ok: boolean; detail: string }> {
  setBrowserPermission(key, true);
  try {
    if (key === 'geolocation') {
      const geo = await readGeo();
      return geo
        ? { ok: true, detail: 'Location access granted.' }
        : { ok: false, detail: 'Location permission was denied or timed out in the browser.' };
    }
    if (key === 'notifications') {
      if (typeof Notification === 'undefined') return { ok: false, detail: 'Notifications are not supported here.' };
      const perm = await Notification.requestPermission();
      return perm === 'granted'
        ? { ok: true, detail: 'Notifications allowed.' }
        : { ok: false, detail: `Notifications are ${perm}.` };
    }
    if (key === 'clipboard') {
      try {
        await navigator.clipboard.writeText('');
        return { ok: true, detail: 'Clipboard access looks available.' };
      } catch {
        return { ok: false, detail: 'Clipboard needs a secure context and a user gesture.' };
      }
    }
    if (key === 'wake_lock') {
      const got = await acquireWakeLock();
      return got ? { ok: true, detail: 'Screen wake lock active while JARVIS needs it.' } : { ok: false, detail: 'Wake lock unavailable in this browser.' };
    }
    if (key === 'battery') {
      const bat = await readBattery();
      return bat ? { ok: true, detail: `Battery ${bat.level_percent}%${bat.charging ? ' (charging)' : ''}.` } : { ok: false, detail: 'Battery API not available.' };
    }
    if (key === 'share') {
      return typeof navigator.share === 'function'
        ? { ok: true, detail: 'Web Share is available.' }
        : { ok: false, detail: 'Web Share is not supported on this device.' };
    }
    if (key === 'files' || key === 'downloads') {
      return { ok: true, detail: 'Ready when JARVIS asks.' };
    }
    if (key === 'camera') {
      if (!navigator.mediaDevices?.getUserMedia) return { ok: false, detail: 'Camera API unavailable.' };
      const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
      stream.getTracks().forEach((t) => t.stop());
      return { ok: true, detail: 'Camera permission granted.' };
    }
    if (key === 'screen_capture') {
      return typeof navigator.mediaDevices?.getDisplayMedia === 'function'
        ? { ok: true, detail: 'Screen capture will prompt when JARVIS asks to capture the screen.' }
        : { ok: false, detail: 'Screen capture is not supported here.' };
    }
    if (key === 'vibrate') {
      try {
        const ok = navigator.vibrate?.(40);
        return ok === false
          ? { ok: false, detail: 'Vibration not supported.' }
          : { ok: true, detail: 'Vibration works on this device.' };
      } catch {
        return { ok: false, detail: 'Vibration not supported.' };
      }
    }
  } catch (error) {
    return { ok: false, detail: error instanceof Error ? error.message : 'Permission request failed.' };
  }
  return { ok: true, detail: 'Saved.' };
}

export async function acquireWakeLock(): Promise<boolean> {
  if (!getBrowserPermissions().wake_lock || !navigator.wakeLock?.request) return false;
  try {
    wakeLock = await navigator.wakeLock.request('screen');
    wakeLock.addEventListener('release', () => { wakeLock = null; });
    return true;
  } catch {
    return false;
  }
}

export async function releaseWakeLock(): Promise<void> {
  try {
    await wakeLock?.release();
  } catch { /* ignore */ }
  wakeLock = null;
}

async function frameFromStream(stream: MediaStream, filename: string): Promise<File> {
  const video = document.createElement('video');
  video.muted = true;
  video.playsInline = true;
  video.srcObject = stream;
  await video.play();
  await new Promise((resolve) => window.setTimeout(resolve, 250));
  const width = video.videoWidth || 1280;
  const height = video.videoHeight || 720;
  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext('2d');
  if (!ctx) throw new Error('Could not capture frame.');
  ctx.drawImage(video, 0, 0, width, height);
  stream.getTracks().forEach((track) => track.stop());
  const blob = await new Promise<Blob>((resolve, reject) => {
    canvas.toBlob((value) => (value ? resolve(value) : reject(new Error('Capture failed.'))), 'image/jpeg', 0.88);
  });
  return new File([blob], filename, { type: 'image/jpeg' });
}

async function uploadCapture(file: File): Promise<Record<string, unknown>> {
  const { api } = await import('./api');
  const record = await api.uploadFile(file);
  return {
    id: record.id,
    filename: record.filename,
    size_bytes: record.size_bytes,
    content_type: record.content_type,
    asset_path: record.asset_path,
  };
}

export type ClientAction = {
  name: string;
  arguments?: Record<string, unknown>;
};

export async function runClientAction(action: ClientAction): Promise<Record<string, unknown>> {
  const prefs = getBrowserPermissions();
  const name = action.name;
  const args = action.arguments || {};

  if (name === 'browser_open_url') {
    const url = String(args.url || '');
    if (!/^https?:\/\//i.test(url)) return { ok: false, error: 'Only http(s) URLs are allowed.' };
    window.open(url, '_blank', 'noopener,noreferrer');
    return { ok: true, opened: url };
  }

  if (name === 'browser_clipboard_write') {
    if (!prefs.clipboard) return { ok: false, error: 'Clipboard permission is off in Settings.' };
    const text = String(args.text || '');
    await navigator.clipboard.writeText(text);
    return { ok: true, bytes: text.length };
  }

  if (name === 'browser_notify') {
    if (!prefs.notifications) return { ok: false, error: 'Notifications are off in Settings.' };
    if (typeof Notification === 'undefined') return { ok: false, error: 'Notifications unsupported.' };
    if (Notification.permission !== 'granted') {
      const perm = await Notification.requestPermission();
      if (perm !== 'granted') return { ok: false, error: 'Notification permission denied.' };
    }
    const title = String(args.title || 'JARVIS');
    const body = String(args.body || args.message || '');
    new Notification(title.slice(0, 120), { body: body.slice(0, 400), silent: false });
    if (prefs.vibrate && typeof navigator.vibrate === 'function') navigator.vibrate([40, 60, 40]);
    return { ok: true, title };
  }

  if (name === 'browser_share') {
    if (!prefs.share || typeof navigator.share !== 'function') {
      return { ok: false, error: 'Web Share is unavailable.' };
    }
    const payload: ShareData = {
      title: args.title ? String(args.title) : undefined,
      text: args.text ? String(args.text) : undefined,
      url: args.url ? String(args.url) : undefined,
    };
    await navigator.share(payload);
    return { ok: true, shared: true };
  }

  if (name === 'browser_wake_lock') {
    const enable = args.enable !== false;
    if (enable) {
      const ok = await acquireWakeLock();
      return { ok, active: ok };
    }
    await releaseWakeLock();
    return { ok: true, active: false };
  }

  if (name === 'browser_vibrate') {
    if (!prefs.vibrate || typeof navigator.vibrate !== 'function') {
      return { ok: false, error: 'Vibration is off or unsupported.' };
    }
    const pattern = Array.isArray(args.pattern)
      ? args.pattern.map((n) => Math.max(0, Math.min(1000, Number(n) || 0))).slice(0, 8)
      : [80, 40, 80];
    navigator.vibrate(pattern);
    return { ok: true, pattern };
  }

  if (name === 'browser_download_text') {
    if (!prefs.downloads) return { ok: false, error: 'Downloads are off in Settings.' };
    const text = String(args.text || '');
    const filename = String(args.filename || 'jarvis-note.txt').replace(/[^\w.\- ()]+/g, '_').slice(0, 120) || 'jarvis-note.txt';
    const blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
    return { ok: true, filename, bytes: text.length };
  }

  if (name === 'browser_pick_files') {
    if (!prefs.files) return { ok: false, error: 'File access is off in Settings.' };
    const input = document.createElement('input');
    input.type = 'file';
    input.multiple = Boolean(args.multiple);
    if (typeof args.accept === 'string' && args.accept.trim()) input.accept = args.accept.trim();
    const files = await new Promise<File[]>((resolve) => {
      input.onchange = () => resolve(Array.from(input.files || []));
      input.oncancel = () => resolve([]);
      input.click();
    });
    const uploaded: Array<Record<string, unknown>> = [];
    for (const file of files.slice(0, 5)) {
      try {
        uploaded.push(await uploadCapture(file));
      } catch (error) {
        uploaded.push({ filename: file.name, error: error instanceof Error ? error.message : 'Upload failed' });
      }
    }
    return { ok: true, files: uploaded };
  }

  if (name === 'browser_camera_capture') {
    if (!prefs.camera) return { ok: false, error: 'Camera is off in Settings.' };
    if (!navigator.mediaDevices?.getUserMedia) return { ok: false, error: 'Camera API unavailable.' };
    const stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: args.facing === 'environment' ? 'environment' : 'user' },
      audio: false,
    });
    const file = await frameFromStream(stream, `jarvis-camera-${Date.now()}.jpg`);
    const uploaded = await uploadCapture(file);
    return { ok: true, capture: 'camera', file: uploaded };
  }

  if (name === 'browser_screen_capture') {
    if (!prefs.screen_capture) return { ok: false, error: 'Screen capture is off in Settings.' };
    if (!navigator.mediaDevices?.getDisplayMedia) return { ok: false, error: 'Screen capture unavailable.' };
    const stream = await navigator.mediaDevices.getDisplayMedia({ video: true, audio: false });
    const file = await frameFromStream(stream, `jarvis-screen-${Date.now()}.jpg`);
    const uploaded = await uploadCapture(file);
    return { ok: true, capture: 'screen', file: uploaded };
  }

  return { ok: false, error: `Unknown client action '${name}'.` };
}
