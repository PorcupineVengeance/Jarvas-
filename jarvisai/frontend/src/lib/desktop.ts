export type JarvisDesktopBridge = {
  isDesktop: boolean;
  platform: string;
  getInfo: () => Promise<{
    isDesktop: boolean;
    platform: string;
    version: string;
    dataPath: string;
    port: number | null;
    computerControl: boolean;
    allowedPaths: string[];
  }>;
  pickFolders: () => Promise<string[]>;
  revealDataDir: () => Promise<boolean>;
  ensureMicrophone?: () => Promise<{ granted: boolean; status: string }>;
  openMicrophoneSettings?: () => Promise<boolean>;
  onAssistantOnline?: () => Promise<boolean>;
  onAssistantStandby?: () => Promise<boolean>;
};

declare global {
  interface Window {
    jarvisDesktop?: JarvisDesktopBridge;
  }
}

export function isJarvisDesktop(): boolean {
  return Boolean(window.jarvisDesktop?.isDesktop);
}

export function desktopPlatform(): string | null {
  return window.jarvisDesktop?.platform ?? null;
}

export async function pickDesktopFolders(): Promise<string[]> {
  if (!window.jarvisDesktop?.pickFolders) return [];
  return window.jarvisDesktop.pickFolders();
}

export async function revealDesktopDataDir(): Promise<void> {
  await window.jarvisDesktop?.revealDataDir?.();
}
