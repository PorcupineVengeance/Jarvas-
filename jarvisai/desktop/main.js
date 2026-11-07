const { app, BrowserWindow, Tray, Menu, nativeImage, dialog, shell, ipcMain, session, systemPreferences, powerSaveBlocker } = require('electron');
const { spawn, execFile } = require('child_process');
const fs = require('fs');
const http = require('http');
const net = require('net');
const path = require('path');

// Keep wake-word listening alive while the window is hidden to the tray.
app.commandLine.appendSwitch('disable-renderer-backgrounding');
app.commandLine.appendSwitch('disable-background-timer-throttling');
app.commandLine.appendSwitch('disable-backgrounding-occluded-windows');

const isDev = process.argv.includes('--dev') || !app.isPackaged;
let mainWindow = null;
let tray = null;
let sidecar = null;
let sidecarPort = null;
let quitting = false;
let powerBlockerId = null;

function userDataPaths() {
  const root = app.getPath('userData');
  return {
    root,
    data: path.join(root, 'data'),
    storage: path.join(root, 'storage'),
    logs: path.join(root, 'logs'),
    envFile: path.join(root, '.env'),
    desktopSettings: path.join(root, 'desktop-settings.json'),
  };
}

function ensureUserDirs() {
  const paths = userDataPaths();
  for (const dir of [paths.root, paths.data, paths.storage, paths.logs]) {
    fs.mkdirSync(dir, { recursive: true });
  }
  if (!fs.existsSync(paths.desktopSettings)) {
    fs.writeFileSync(
      paths.desktopSettings,
      JSON.stringify(
        {
          computer_control: true,
          live_web: true,
          bluetooth: false,
          full_device_access: false,
          allowed_paths: ['~/Desktop', '~/Documents', '~/Downloads'],
        },
        null,
        2,
      ),
      'utf8',
    );
  }
  return paths;
}

function readDesktopSettings() {
  const { desktopSettings } = userDataPaths();
  try {
    return JSON.parse(fs.readFileSync(desktopSettings, 'utf8'));
  } catch {
    return { computer_control: true, live_web: true, bluetooth: false, full_device_access: false, allowed_paths: ['~/Desktop', '~/Documents', '~/Downloads'] };
  }
}

function resourcePath(...parts) {
  if (app.isPackaged) {
    return path.join(process.resourcesPath, ...parts);
  }
  return path.join(__dirname, 'resources', ...parts);
}

function projectRoot() {
  return path.resolve(__dirname, '..');
}

function findFreePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.listen(0, '127.0.0.1', () => {
      const address = server.address();
      const port = typeof address === 'object' && address ? address.port : 0;
      server.close((err) => (err ? reject(err) : resolve(port)));
    });
    server.on('error', reject);
  });
}

function waitForHealth(port, timeoutMs = 45000) {
  const started = Date.now();
  return new Promise((resolve, reject) => {
    const tick = () => {
      const req = http.get({ host: '127.0.0.1', port, path: '/api/health', timeout: 2000 }, (res) => {
        res.resume();
        if (res.statusCode && res.statusCode < 500) {
          resolve();
          return;
        }
        retry();
      });
      req.on('error', retry);
      req.on('timeout', () => {
        req.destroy();
        retry();
      });
    };
    const retry = () => {
      if (Date.now() - started > timeoutMs) {
        reject(new Error('JARVIS backend did not become ready in time.'));
        return;
      }
      setTimeout(tick, 400);
    };
    tick();
  });
}

function seedEnvFromProject(paths) {
  if (fs.existsSync(paths.envFile)) return;
  const candidates = [
    path.join(projectRoot(), '.env'),
    path.join(projectRoot(), '.env.example'),
  ];
  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) {
      fs.copyFileSync(candidate, paths.envFile);
      return;
    }
  }
  fs.writeFileSync(
    paths.envFile,
    [
      'JARVIS_OPEN_ACCESS=true',
      'JARVIS_LOCAL_AUTH_ENABLED=true',
      'JARVIS_LOCAL_AUTH_SECRET=jarvis-desktop-local-secret',
      'JARVIS_RESEARCH_PROVIDER=duckduckgo',
      '',
    ].join('\n'),
    'utf8',
  );
}

function sidecarEnv(paths, port) {
  const settings = readDesktopSettings();
  const allowed = Array.isArray(settings.allowed_paths) ? settings.allowed_paths.join(',') : '~/Desktop,~/Documents,~/Downloads';
  const computer = settings.computer_control !== false;
  const liveWeb = settings.live_web !== false;
  const bluetooth = settings.bluetooth === true;
  const fullDevice = settings.full_device_access === true;
  const frontendDir = app.isPackaged
    ? resourcePath('frontend')
    : path.join(projectRoot(), 'frontend', 'dist');
  return {
    ...process.env,
    JARVIS_DESKTOP: '1',
    JARVIS_ENABLE_COMPUTER_CONTROL: computer ? 'true' : 'false',
    JARVIS_ENABLE_LIVE_WEB: liveWeb ? 'true' : 'false',
    JARVIS_ENABLE_BLUETOOTH: bluetooth ? 'true' : 'false',
    JARVIS_ENABLE_FULL_DEVICE_ACCESS: fullDevice && computer ? 'true' : 'false',
    JARVIS_ALLOWED_PATHS: allowed,
    JARVIS_STORAGE_DIR: paths.storage,
    DATABASE_URL: `sqlite:///${path.join(paths.data, 'jarvis.db')}`,
    JARVIS_DESKTOP_SETTINGS_PATH: paths.desktopSettings,
    JARVIS_FRONTEND_DIR: frontendDir,
    PYTHONUNBUFFERED: '1',
    PORT: String(port),
  };
}

function resolveSidecarCommand(paths, port) {
  const env = sidecarEnv(paths, port);
  if (app.isPackaged) {
    const binaryName = process.platform === 'win32' ? 'jarvis-sidecar.exe' : 'jarvis-sidecar';
    const binary = resourcePath('sidecar', binaryName);
    if (!fs.existsSync(binary)) {
      throw new Error(`Packaged sidecar missing at ${binary}. Build it with desktop/scripts/build-sidecar.sh first.`);
    }
    return { command: binary, args: ['--host', '127.0.0.1', '--port', String(port)], env, cwd: paths.root };
  }

  // Dev: run uvicorn against the local project with PYTHONPATH=backend.
  const pythonCandidates = [
    path.join(projectRoot(), '.venv', 'bin', 'python'),
    path.join(projectRoot(), '.venv', 'Scripts', 'python.exe'),
    process.platform === 'win32' ? 'python' : 'python3',
  ];
  const python = pythonCandidates.find((candidate) => candidate === 'python' || candidate === 'python3' || fs.existsSync(candidate));
  return {
    command: python,
    args: ['-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', String(port)],
    env: {
      ...env,
      PYTHONPATH: path.join(projectRoot(), 'backend'),
    },
    cwd: projectRoot(),
  };
}

async function startSidecar() {
  const paths = ensureUserDirs();
  seedEnvFromProject(paths);
  sidecarPort = await findFreePort();
  const launch = resolveSidecarCommand(paths, sidecarPort);
  console.log(`[desktop] starting sidecar on ${sidecarPort}: ${launch.command} ${launch.args.join(' ')}`);
  sidecar = spawn(launch.command, launch.args, {
    cwd: launch.cwd,
    env: launch.env,
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  sidecar.stdout.on('data', (chunk) => console.log(`[sidecar] ${chunk}`.trimEnd()));
  sidecar.stderr.on('data', (chunk) => console.error(`[sidecar] ${chunk}`.trimEnd()));
  sidecar.on('error', (err) => console.error('[sidecar] spawn error', err));
  sidecar.on('exit', (code) => {
    console.log(`[sidecar] exited with code ${code}`);
    sidecar = null;
    if (!quitting && mainWindow && !mainWindow.isDestroyed()) {
      dialog.showErrorBox('JARVIS', 'The local assistant backend stopped unexpectedly.');
    }
  });
  await waitForHealth(sidecarPort);
  console.log(`[desktop] sidecar healthy on ${sidecarPort}`);
  return sidecarPort;
}

function stopSidecar() {
  if (!sidecar || sidecar.killed) return;
  try {
    if (process.platform === 'win32') {
      execFile('taskkill', ['/pid', String(sidecar.pid), '/f', '/t'], () => undefined);
    } else {
      sidecar.kill('SIGTERM');
    }
  } catch (err) {
    console.error('Failed to stop sidecar', err);
  }
  sidecar = null;
}

function loadTrayIcon() {
  const iconFile = resourcePath('icon.png');
  if (fs.existsSync(iconFile)) {
    return nativeImage.createFromPath(iconFile);
  }
  // 16x16 red pixel fallback so tray still appears without assets.
  const png = Buffer.from(
    'iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAFUlEQVQ4T2NkYGD4z0ABYBw1gGE0DAB+4ABu6V8qXgAAAABJRU5ErkJggg==',
    'base64',
  );
  return nativeImage.createFromBuffer(png);
}

function createTray() {
  const icon = loadTrayIcon();
  tray = new Tray(icon.resize({ width: 16, height: 16 }));
  tray.setToolTip('JARVIS');
  const contextMenu = Menu.buildFromTemplate([
    {
      label: 'Show JARVIS',
      click: () => {
        if (mainWindow) {
          mainWindow.show();
          mainWindow.focus();
        }
      },
    },
    {
      label: 'Hide',
      click: () => mainWindow?.hide(),
    },
    { type: 'separator' },
    {
      label: 'Quit',
      click: () => {
        quitting = true;
        app.quit();
      },
    },
  ]);
  tray.setContextMenu(contextMenu);
  tray.on('click', () => {
    if (!mainWindow) return;
    if (mainWindow.isVisible()) mainWindow.hide();
    else {
      mainWindow.show();
      mainWindow.focus();
    }
  });
}

async function ensureMicrophoneAccess() {
  if (process.platform !== 'darwin' || typeof systemPreferences?.askForMediaAccess !== 'function') {
    return true;
  }
  try {
    const status = systemPreferences.getMediaAccessStatus('microphone');
    console.log(`[desktop] microphone access status: ${status}`);
    if (status === 'granted') return true;
    const allowed = await systemPreferences.askForMediaAccess('microphone');
    console.log(`[desktop] microphone ask result: ${allowed}`);
    return Boolean(allowed);
  } catch (err) {
    console.error('[desktop] microphone permission request failed', err);
    return false;
  }
}

function allowMediaPermissions() {
  const ses = session.defaultSession;
  ses.setPermissionRequestHandler((_webContents, permission, callback) => {
    if (permission === 'media' || permission === 'microphone' || permission === 'audioCapture') {
      callback(true);
      return;
    }
    callback(false);
  });
  ses.setPermissionCheckHandler((_webContents, permission) => {
    return permission === 'media' || permission === 'microphone' || permission === 'audioCapture';
  });
}

function createWindow(port) {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 840,
    minWidth: 960,
    minHeight: 640,
    title: 'JARVIS',
    backgroundColor: '#0a0a0c',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      backgroundThrottling: false,
    },
  });

  const url = `http://127.0.0.1:${port}/`;
  mainWindow.loadURL(url);
  // DevTools only when explicitly requested — it steals focus and confuses voice UX.
  if (isDev && process.env.JARVIS_DESKTOP_DEVTOOLS === '1') {
    mainWindow.webContents.openDevTools({ mode: 'detach' });
  }

  // Closing the window keeps JARVIS in the tray so Hey/Yo still works.
  mainWindow.on('close', (event) => {
    if (!quitting) {
      event.preventDefault();
      mainWindow.hide();
    }
  });
}

function registerIpc() {
  ipcMain.handle('desktop:get-info', async () => {
    const paths = userDataPaths();
    const settings = readDesktopSettings();
    return {
      isDesktop: true,
      platform: process.platform,
      version: app.getVersion(),
      dataPath: paths.root,
      port: sidecarPort,
      computerControl: settings.computer_control !== false,
      allowedPaths: settings.allowed_paths || [],
    };
  });

  ipcMain.handle('desktop:pick-folders', async () => {
    const result = await dialog.showOpenDialog(mainWindow, {
      properties: ['openDirectory', 'multiSelections'],
      title: 'Choose folders JARVIS may access',
    });
    if (result.canceled) return [];
    return result.filePaths;
  });

  ipcMain.handle('desktop:reveal-data-dir', async () => {
    const { root } = userDataPaths();
    await shell.openPath(root);
    return true;
  });

  ipcMain.handle('desktop:ensure-microphone', async () => {
    const granted = await ensureMicrophoneAccess();
    const status =
      process.platform === 'darwin' && typeof systemPreferences?.getMediaAccessStatus === 'function'
        ? systemPreferences.getMediaAccessStatus('microphone')
        : granted
          ? 'granted'
          : 'unknown';
    return { granted: Boolean(granted), status };
  });

  ipcMain.handle('desktop:open-microphone-settings', async () => {
    if (process.platform === 'darwin') {
      await shell.openExternal(
        'x-apple.systempreferences:com.apple.settings.PrivacySecurity.extension?Privacy_Microphone',
      );
      return true;
    }
    return false;
  });

  // Voice session hooks — do not force the window forward; standby wake works from tray.
  ipcMain.handle('desktop:assistant-online', async () => {
    if (tray) tray.setToolTip('JARVIS · online');
    return true;
  });
  ipcMain.handle('desktop:assistant-standby', async () => {
    if (tray) tray.setToolTip('JARVIS · standby (say Hey JARVIS)');
    return true;
  });
}

app.whenReady().then(async () => {
  try {
    allowMediaPermissions();
    // Keep timers/mic wake loop alive while hidden.
    try {
      powerBlockerId = powerSaveBlocker.start('prevent-app-suspension');
    } catch (err) {
      console.warn('[desktop] powerSaveBlocker unavailable', err);
    }
    // Don't block backend startup on the mic prompt — voice can request it later.
    void ensureMicrophoneAccess().then((micOk) => {
      if (!micOk && process.platform === 'darwin') {
        void dialog.showMessageBox({
          type: 'warning',
          title: 'Microphone access',
          message: 'JARVIS needs microphone access to talk with you.',
          detail: 'Enable Microphone for Electron (or JARVIS) in macOS System Settings → Privacy & Security → Microphone, then restart the app.',
        });
      }
    });
    registerIpc();
    const port = await startSidecar();
    createTray();
    createWindow(port);
    if (tray) tray.setToolTip('JARVIS · standby (say Hey JARVIS)');
  } catch (err) {
    console.error(err);
    dialog.showErrorBox('JARVIS failed to start', err instanceof Error ? err.message : String(err));
    quitting = true;
    app.quit();
  }
});

app.on('before-quit', () => {
  quitting = true;
  if (powerBlockerId != null && powerSaveBlocker.isStarted(powerBlockerId)) {
    try { powerSaveBlocker.stop(powerBlockerId); } catch { /* ignore */ }
  }
  powerBlockerId = null;
  stopSidecar();
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    quitting = true;
    app.quit();
  }
});

app.on('activate', () => {
  if (mainWindow) {
    mainWindow.show();
  }
});
