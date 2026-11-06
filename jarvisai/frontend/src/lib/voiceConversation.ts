/** Browser voice helpers for JARVIS talk-back conversations. */

export const DEFAULT_FISH_VOICE = '41f0953d7a6b4c078445c7e65d620eeb';

export function getPreferredVoice(): string {
  try {
    return localStorage.getItem('jarvis.tts_voice')?.trim() || DEFAULT_FISH_VOICE;
  } catch {
    return DEFAULT_FISH_VOICE;
  }
}

export function setPreferredVoice(voiceId: string): void {
  try {
    localStorage.setItem('jarvis.tts_voice', voiceId.trim() || DEFAULT_FISH_VOICE);
  } catch {
    /* ignore quota / private mode */
  }
}

export function stripForSpeech(text: string): string {
  return text
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/!\[[^\]]*]\([^)]*\)/g, ' ')
    .replace(/\[[^\]]*]\([^)]*\)/g, '$1')
    .replace(/[#>*_~|]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, 1800);
}

/** Full reply for TTS — keep the complete thought, not a truncated fragment. */
export function forSpeech(text: string, maxChars = 700): string {
  return stripForSpeech(text).slice(0, maxChars);
}

/** @deprecated use forSpeech — kept so older imports keep working */
export function forFastVoice(text: string): string {
  return forSpeech(text);
}

/**
 * First finished sentence only (ends with . ! or ?).
 * Never returns a mid-clause fragment.
 */
export function firstVoiceChunk(text: string, maxChars = 320): string | null {
  const clean = stripForSpeech(text);
  if (!clean) return null;
  const match = clean.match(/^(.+?[.!?])(?:\s|$)/);
  if (match && match[1].trim().length >= 8) {
    return match[1].trim().slice(0, maxChars);
  }
  return null;
}

let micReady = false;

export async function ensureMicrophonePermissionCached(): Promise<void> {
  if (micReady) return;
  await ensureMicrophonePermission();
  micReady = true;
}

type SpeechRecognitionLike = {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  maxAlternatives: number;
  start: () => void;
  stop: () => void;
  abort: () => void;
  onstart: ((event: Event) => void) | null;
  onerror: ((event: Event & { error?: string }) => void) | null;
  onend: ((event: Event) => void) | null;
  onresult: ((event: Event & { resultIndex: number; results: ArrayLike<{ isFinal: boolean; 0: { transcript: string } }> }) => void) | null;
};

function getSpeechRecognitionCtor(): (new () => SpeechRecognitionLike) | null {
  const w = window as Window & {
    SpeechRecognition?: new () => SpeechRecognitionLike;
    webkitSpeechRecognition?: new () => SpeechRecognitionLike;
  };
  return w.SpeechRecognition || w.webkitSpeechRecognition || null;
}

export function browserSpeechSupported(): boolean {
  return Boolean(getSpeechRecognitionCtor());
}

/** Prefer Whisper/server STT whenever it is configured — browser ASR is flaky in Electron and some Chromium builds. */
export function shouldUseServerStt(sttReady: boolean): boolean {
  if (!sttReady) return false;
  try {
    if (localStorage.getItem('jarvis.prefer_browser_asr') === 'true' && browserSpeechSupported()) return false;
  } catch { /* ignore */ }
  return true;
}

/**
 * Matches "hey/yo/hi/ok jarvis" (+ optional command).
 * Also accepts Whisper misspellings (jarvus/jarvish) and bare "jarvis"
 * when the leading "hey/yo" was clipped by VAD.
 */
const WAKE_NAME = String.raw`jarv(?:is|us|ish)|jarves|jarvice|jarviz`;
const WAKE_RE = new RegExp(
  String.raw`\b((?:hey|hi|yo|okay|ok|a|eh|oh)\s*,?\s*)?(${WAKE_NAME})\b[,.!]?\s*(.*)$`,
  'i',
);

export function matchWakePhrase(text: string): { matched: boolean; command: string; trigger: string } {
  const normalized = text
    .trim()
    .replace(/[""]/g, '"')
    .replace(/['']/g, "'")
    .replace(/[^\w\s'.,!?-]+/g, ' ')
    .replace(/\s+/g, ' ');
  if (!normalized) return { matched: false, command: '', trigger: '' };
  const match = normalized.match(WAKE_RE);
  if (!match) return { matched: false, command: '', trigger: '' };
  const prefix = (match[1] || '').trim();
  const name = (match[2] || '').trim();
  const command = (match[3] || '').trim();
  // Bare "Jarvis" only counts near the start (clipped “Hey”), not mid-sentence noise.
  if (!prefix) {
    const idx = normalized.toLowerCase().search(/jarv(?:is|us|ish)|jarves|jarvice|jarviz/);
    if (idx > 28) return { matched: false, command: '', trigger: '' };
  }
  return {
    matched: true,
    trigger: `${prefix} ${name}`.trim(),
    command,
  };
}

export function isWakeWordEnabled(): boolean {
  try {
    const stored = localStorage.getItem('jarvis.wake_word');
    if (stored === 'true') return true;
    if (stored === 'false') return false;
  } catch { /* ignore */ }
  // Desktop defaults to on so “Hey/Yo JARVIS” works immediately.
  return Boolean(typeof window !== 'undefined' && window.jarvisDesktop?.isDesktop);
}

export function setWakeWordEnabled(enabled: boolean): void {
  try {
    localStorage.setItem('jarvis.wake_word', enabled ? 'true' : 'false');
  } catch { /* ignore */ }
  window.dispatchEvent(new CustomEvent('jarvis:wake-word-pref', { detail: { enabled } }));
}

export type WakeWordHandle = { stop: () => void };

/**
 * Listen for "Hey JARVIS" / "Yo JARVIS" in the background.
 * Uses a rolling Whisper buffer (with pre-roll so “Hey” isn’t clipped) and
 * browser ASR in parallel when available.
 */
export function startWakeWordMonitor(options: {
  onWake: (heard: string, command: string) => void;
  sttReady?: boolean;
  transcribe?: (file: File) => Promise<string>;
}): WakeWordHandle {
  let stopped = false;
  let busy = false;
  let recognition: SpeechRecognitionLike | null = null;
  let mediaCleanup: (() => void) | null = null;
  let restartTimer = 0;

  const pauseForCall = () => Boolean((window as Window & { __jarvisVoiceBusy?: boolean }).__jarvisVoiceBusy);

  const publishStatus = (detail: { state: string; heard?: string }) => {
    try {
      window.dispatchEvent(new CustomEvent('jarvis:wake-status', { detail }));
    } catch { /* ignore */ }
  };

  const emitWake = (heard: string) => {
    if (stopped || busy || pauseForCall()) return;
    publishStatus({ state: 'heard', heard });
    const hit = matchWakePhrase(heard);
    if (!hit.matched) return;
    busy = true;
    publishStatus({ state: 'wake', heard });
    try { options.onWake(heard, hit.command); } finally {
      window.setTimeout(() => { busy = false; }, 2200);
    }
  };

  const startBrowserWake = (): boolean => {
    const Ctor = getSpeechRecognitionCtor();
    if (!Ctor) return false;
    const rec = new Ctor();
    recognition = rec;
    rec.continuous = true;
    rec.interimResults = true;
    rec.lang = navigator.language || 'en-US';
    rec.maxAlternatives = 3;
    let rolling = '';
    rec.onresult = (event) => {
      let chunk = '';
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        chunk += ` ${event.results[i][0]?.transcript || ''}`;
      }
      const text = chunk.trim();
      if (!text) return;
      rolling = `${rolling} ${text}`.trim().slice(-180);
      emitWake(text);
      if (!busy) emitWake(rolling);
    };
    rec.onerror = (event) => {
      const code = event.error || '';
      if (code === 'aborted' || stopped) return;
      if (restartTimer) window.clearTimeout(restartTimer);
      restartTimer = window.setTimeout(() => {
        if (stopped || pauseForCall()) return;
        try { rec.start(); } catch { /* ignore */ }
      }, 700);
    };
    rec.onend = () => {
      if (stopped || pauseForCall()) return;
      try { rec.start(); } catch { /* ignore */ }
    };
    try {
      rec.start();
      publishStatus({ state: 'browser-listening' });
      return true;
    } catch {
      recognition = null;
      return false;
    }
  };

  const startVadWake = async () => {
    if (!options.sttReady || !options.transcribe) return;
    if (!navigator.mediaDevices?.getUserMedia) return;
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
        channelCount: 1,
      },
    });
    if (stopped) {
      stream.getTracks().forEach((t) => t.stop());
      return;
    }
    const audioContext = new AudioContext({ sampleRate: 16000 });
    try {
      if (audioContext.state === 'suspended') await audioContext.resume();
    } catch { /* ignore */ }
    const source = audioContext.createMediaStreamSource(stream);
    const analyser = audioContext.createAnalyser();
    analyser.fftSize = 2048;
    analyser.smoothingTimeConstant = 0.35;
    source.connect(analyser);

    // PCM ring buffer — valid WAV for Whisper (MediaRecorder slice concat breaks on Electron/mp4).
    const sampleRate = audioContext.sampleRate;
    const PRE_ROLL_SEC = 1.4;
    const MAX_CAPTURE_SEC = 4.2;
    const ring = new Float32Array(Math.ceil(sampleRate * (PRE_ROLL_SEC + MAX_CAPTURE_SEC + 0.5)));
    let ringWrite = 0;
    let ringFilled = 0;
    let capturing = false;
    let captureSamples = 0;
    let captureTarget = 0;
    let quietMs = 0;
    let loudFor = 0;
    let last = performance.now();
    let raf = 0;
    const timeData = new Uint8Array(analyser.fftSize);

    const processor = audioContext.createScriptProcessor(4096, 1, 1);
    processor.onaudioprocess = (event) => {
      const input = event.inputBuffer.getChannelData(0);
      for (let i = 0; i < input.length; i += 1) {
        ring[ringWrite] = input[i];
        ringWrite = (ringWrite + 1) % ring.length;
        if (ringFilled < ring.length) ringFilled += 1;
      }
      if (capturing) {
        captureSamples += input.length;
        if (captureSamples >= captureTarget && quietMs > 350) {
          // tick() finalizes; mark ready by setting target hit
          captureTarget = Math.min(captureTarget, captureSamples);
        }
      }
    };
    source.connect(processor);
    // Keep the processor graph alive without audible output.
    const mute = audioContext.createGain();
    mute.gain.value = 0;
    processor.connect(mute);
    mute.connect(audioContext.destination);

    const cleanup = () => {
      if (raf) cancelAnimationFrame(raf);
      try { processor.disconnect(); } catch { /* ignore */ }
      try { mute.disconnect(); } catch { /* ignore */ }
      try { source.disconnect(); } catch { /* ignore */ }
      void audioContext.close().catch(() => undefined);
      stream.getTracks().forEach((t) => t.stop());
      mediaCleanup = null;
    };
    mediaCleanup = cleanup;

    const rmsNow = () => {
      analyser.getByteTimeDomainData(timeData);
      let sum = 0;
      for (let i = 0; i < timeData.length; i += 1) {
        const v = (timeData[i] - 128) / 128;
        sum += v * v;
      }
      return Math.sqrt(sum / timeData.length);
    };

    const readRing = (sampleCount: number): Float32Array => {
      const count = Math.min(sampleCount, ringFilled);
      const out = new Float32Array(count);
      let idx = (ringWrite - count + ring.length) % ring.length;
      for (let i = 0; i < count; i += 1) {
        out[i] = ring[idx];
        idx = (idx + 1) % ring.length;
      }
      return out;
    };

    const pcmToWavFile = (pcm: Float32Array): File => {
      const buffer = new ArrayBuffer(44 + pcm.length * 2);
      const view = new DataView(buffer);
      const writeStr = (offset: number, value: string) => {
        for (let i = 0; i < value.length; i += 1) view.setUint8(offset + i, value.charCodeAt(i));
      };
      writeStr(0, 'RIFF');
      view.setUint32(4, 36 + pcm.length * 2, true);
      writeStr(8, 'WAVE');
      writeStr(12, 'fmt ');
      view.setUint32(16, 16, true);
      view.setUint16(20, 1, true);
      view.setUint16(22, 1, true);
      view.setUint32(24, sampleRate, true);
      view.setUint32(28, sampleRate * 2, true);
      view.setUint16(32, 2, true);
      view.setUint16(34, 16, true);
      writeStr(36, 'data');
      view.setUint32(40, pcm.length * 2, true);
      let offset = 44;
      for (let i = 0; i < pcm.length; i += 1) {
        const s = Math.max(-1, Math.min(1, pcm[i]));
        view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true);
        offset += 2;
      }
      return new File([buffer], 'wake.wav', { type: 'audio/wav' });
    };

    const captureClip = async () => {
      if (capturing || stopped || busy || pauseForCall()) return;
      capturing = true;
      quietMs = 0;
      captureSamples = 0;
      // Keep recording until silence; include pre-roll from the ring.
      captureTarget = Math.ceil(sampleRate * 0.85);
      const maxSamples = Math.ceil(sampleRate * MAX_CAPTURE_SEC);
      publishStatus({ state: 'capturing' });
      try {
        await new Promise<void>((resolve) => {
          const started = performance.now();
          const wait = () => {
            if (stopped || pauseForCall()) {
              resolve();
              return;
            }
            const elapsed = performance.now() - started;
            const rms = rmsNow();
            if (rms > 0.011) {
              quietMs = 0;
              captureTarget = Math.min(maxSamples, captureSamples + Math.ceil(sampleRate * 0.55));
            } else {
              quietMs += 40;
            }
            if ((quietMs > 380 && captureSamples >= Math.ceil(sampleRate * 0.6)) || captureSamples >= maxSamples || elapsed > 4500) {
              resolve();
              return;
            }
            window.setTimeout(wait, 40);
          };
          wait();
        });
        if (stopped || pauseForCall()) return;
        const total = Math.min(
          ringFilled,
          Math.ceil(sampleRate * PRE_ROLL_SEC) + captureSamples,
        );
        const pcm = readRing(total);
        if (pcm.length < sampleRate * 0.25) {
          publishStatus({ state: 'empty' });
          return;
        }
        const file = pcmToWavFile(pcm);
        const text = (await options.transcribe!(file)).trim();
        if (text) {
          console.info('[jarvis-wake] heard:', text);
          emitWake(text);
        } else {
          publishStatus({ state: 'empty' });
        }
      } catch (error) {
        console.warn('[jarvis-wake] capture failed', error);
        publishStatus({ state: 'error' });
      } finally {
        capturing = false;
        loudFor = 0;
        quietMs = 0;
        captureSamples = 0;
        if (!stopped && !pauseForCall()) publishStatus({ state: 'listening' });
      }
    };

    const tick = (now: number) => {
      const dt = now - last;
      last = now;
      if (stopped) return;
      try {
        if (audioContext.state === 'suspended') void audioContext.resume();
      } catch { /* ignore */ }
      if (pauseForCall() || busy || capturing) {
        if (!capturing) loudFor = 0;
        raf = requestAnimationFrame(tick);
        return;
      }
      const rms = rmsNow();
      if (rms > 0.010) {
        loudFor += dt;
        if (loudFor > 70) void captureClip();
      } else {
        loudFor = 0;
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    publishStatus({ state: 'listening' });
  };

  // Whisper rolling buffer on desktop/STT. Browser ASR only as fallback — both
  // fighting for the mic in Electron is a common reason wake never fires.
  const canVad = Boolean(options.sttReady && options.transcribe);
  if (canVad) {
    void startVadWake().catch((error) => {
      console.warn('[jarvis-wake] vad failed, trying browser ASR', error);
      publishStatus({ state: 'error' });
      if (!startBrowserWake()) publishStatus({ state: 'unavailable' });
    });
  } else if (!startBrowserWake()) {
    publishStatus({ state: 'unavailable' });
  }

  return {
    stop: () => {
      stopped = true;
      if (restartTimer) window.clearTimeout(restartTimer);
      try { recognition?.abort(); } catch { /* ignore */ }
      recognition = null;
      mediaCleanup?.();
      publishStatus({ state: 'stopped' });
    },
  };
}

export function setVoiceBusy(busy: boolean): void {
  const previous = Boolean((window as Window & { __jarvisVoiceBusy?: boolean }).__jarvisVoiceBusy);
  (window as Window & { __jarvisVoiceBusy?: boolean }).__jarvisVoiceBusy = busy;
  if (previous === busy) return;
  // Let the wake-word monitor fully release the mic while a call is active.
  window.dispatchEvent(new CustomEvent(busy ? 'jarvis:voice-busy' : 'jarvis:voice-idle'));
}

export type LiveListenHandle = {
  stop: () => void;
  promise: Promise<string>;
};

/** Prefer native browser speech recognition for conversational turn-taking. */
export function startBrowserListen(options?: {
  lang?: string;
  onPartial?: (text: string) => void;
  /** End the turn this long after the last final phrase (ChatGPT-style pause). */
  endSilenceMs?: number;
  maxMs?: number;
}): LiveListenHandle {
  const Ctor = getSpeechRecognitionCtor();
  if (!Ctor) {
    return {
      stop: () => undefined,
      promise: Promise.reject(new Error('Browser speech recognition is not available in this browser. Use Chrome or Edge.')),
    };
  }

  let settled = false;
  let resolveText!: (text: string) => void;
  let rejectText!: (error: Error) => void;
  const promise = new Promise<string>((resolve, reject) => {
    resolveText = resolve;
    rejectText = reject;
  });

  const recognition = new Ctor();
  recognition.continuous = true;
  recognition.interimResults = true;
  recognition.lang = options?.lang || navigator.language || 'en-US';
  recognition.maxAlternatives = 1;

  let finalText = '';
  let endTimer = 0;
  const endSilenceMs = options?.endSilenceMs ?? 500;
  const maxMs = options?.maxMs ?? 14_000;

  const finish = (text: string) => {
    if (settled) return;
    settled = true;
    if (endTimer) window.clearTimeout(endTimer);
    if (maxTimer) window.clearTimeout(maxTimer);
    try { recognition.stop(); } catch { /* ignore */ }
    resolveText(text.trim());
  };

  const bumpEndTimer = () => {
    if (endTimer) window.clearTimeout(endTimer);
    if (!finalText.trim()) return;
    endTimer = window.setTimeout(() => finish(finalText), endSilenceMs);
  };

  recognition.onresult = (event) => {
    let interim = '';
    for (let i = event.resultIndex; i < event.results.length; i += 1) {
      const piece = event.results[i][0]?.transcript || '';
      if (event.results[i].isFinal) {
        finalText = `${finalText} ${piece}`.trim();
        bumpEndTimer();
      } else {
        interim += piece;
      }
    }
    options?.onPartial?.(`${finalText}${interim ? ` ${interim}` : ''}`.trim());
  };
  recognition.onerror = (event) => {
    const code = event.error || 'unknown';
    if (code === 'aborted' || code === 'no-speech') {
      finish(finalText);
      return;
    }
    if (settled) return;
    settled = true;
    if (endTimer) window.clearTimeout(endTimer);
    if (maxTimer) window.clearTimeout(maxTimer);
    if (code === 'not-allowed' || code === 'service-not-allowed') {
      rejectText(new Error('Microphone permission was denied. Allow the mic for this site in your browser settings, then click JARVIS again.'));
      return;
    }
    // Soft failures: return whatever we heard so the call can continue.
    if (finalText.trim()) {
      resolveText(finalText.trim());
      return;
    }
    rejectText(new Error(`Speech recognition failed (${code}). Try again or type your message.`));
  };
  recognition.onend = () => {
    if (settled) return;
    // Chrome sometimes ends mid-turn; keep listening if we have nothing yet and call is open.
    if (!finalText.trim()) {
      try {
        recognition.start();
        return;
      } catch {
        finish('');
        return;
      }
    }
    finish(finalText);
  };

  const maxTimer = window.setTimeout(() => finish(finalText), maxMs);

  try {
    recognition.start();
  } catch (error) {
    settled = true;
    window.clearTimeout(maxTimer);
    rejectText(error instanceof Error ? error : new Error('Could not start the microphone.'));
  }

  return {
    promise,
    stop: () => finish(finalText),
  };
}

export type RecordingHandle = {
  stop: () => void;
  promise: Promise<File>;
};

export async function ensureMicrophonePermission(): Promise<void> {
  if (!navigator.mediaDevices?.getUserMedia) {
    throw new Error('This browser does not support microphone access. Use Chrome or Edge over http://localhost.');
  }
  const desktop = Boolean(window.jarvisDesktop?.isDesktop);
  try {
    // Ask the Electron shell to re-prompt / open macOS mic settings when needed.
    if (desktop) {
      try { await window.jarvisDesktop?.ensureMicrophone?.(); } catch { /* continue to getUserMedia */ }
    }
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
    stream.getTracks().forEach((track) => track.stop());
  } catch (error) {
    const name = error instanceof DOMException ? error.name : '';
    if (name === 'NotAllowedError' || name === 'PermissionDeniedError') {
      if (desktop) {
        try { await window.jarvisDesktop?.openMicrophoneSettings?.(); } catch { /* ignore */ }
        throw new Error(
          'Microphone is blocked for JARVIS Desktop. In macOS System Settings → Privacy & Security → Microphone, enable Electron (or JARVIS), then quit and reopen the app.',
        );
      }
      throw new Error('Microphone blocked. Click the lock/site settings icon in the address bar, allow Microphone, then click JARVIS again.');
    }
    if (name === 'NotFoundError' || name === 'DevicesNotFoundError') {
      throw new Error('No microphone was found. Plug one in (or enable it in macOS System Settings → Privacy & Security → Microphone), then try again.');
    }
    throw error instanceof Error ? error : new Error('Could not open the microphone.');
  }
}

export async function startVoiceCapture(options?: {
  maxMs?: number;
  silenceMs?: number;
  minMs?: number;
  onLevel?: (level: number) => void;
}): Promise<RecordingHandle> {
  if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
    throw new Error('This browser does not support microphone recording.');
  }
  const deviceStream = await navigator.mediaDevices.getUserMedia({
    audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
  });
  const preferred = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
    ? 'audio/webm;codecs=opus'
    : MediaRecorder.isTypeSupported('audio/mp4')
      ? 'audio/mp4'
      : MediaRecorder.isTypeSupported('audio/wav')
        ? 'audio/wav'
        : undefined;
  const recorder = new MediaRecorder(deviceStream, preferred ? { mimeType: preferred } : undefined);
  const chunks: Blob[] = [];
  let settled = false;
  let stopping = false;
  let resolveFile!: (file: File) => void;
  let rejectFile!: (error: Error) => void;
  const promise = new Promise<File>((resolve, reject) => {
    resolveFile = resolve;
    rejectFile = reject;
  });

  const audioContext = new AudioContext();
  // Critical in Electron/Chromium: after async mic permission, context often stays suspended
  // and VAD never sees speech — the turn never ends.
  try {
    if (audioContext.state === 'suspended') await audioContext.resume();
  } catch { /* ignore */ }
  const source = audioContext.createMediaStreamSource(deviceStream);
  const analyser = audioContext.createAnalyser();
  analyser.fftSize = 2048;
  analyser.smoothingTimeConstant = 0.3;
  source.connect(analyser);
  const data = new Uint8Array(analyser.fftSize);
  let heardSpeech = false;
  let speechStartedAt = 0;
  let silentFor = 0;
  let lastTick = performance.now();
  let raf = 0;
  const silenceMs = options?.silenceMs ?? 1200;
  const maxMs = options?.maxMs ?? 30_000;
  const minMs = options?.minMs ?? 1200;
  // Slightly forgiving threshold for laptop mics / Electron gain.
  const speechThreshold = 0.015;

  const cleanupAudio = () => {
    if (raf) cancelAnimationFrame(raf);
    try { source.disconnect(); } catch { /* ignore */ }
    void audioContext.close().catch(() => undefined);
    deviceStream.getTracks().forEach((track) => track.stop());
  };

  const finish = () => {
    if (settled || stopping) return;
    stopping = true;
    try {
      if (recorder.state === 'recording') {
        try { recorder.requestData(); } catch { /* ignore */ }
        recorder.stop();
      } else if (recorder.state === 'inactive') {
        // Already stopped somehow — resolve from whatever we have.
        settled = true;
        cleanupAudio();
        const blob = new Blob(chunks, { type: recorder.mimeType || 'audio/webm' });
        if (!blob.size) {
          rejectFile(new Error('No audio was captured. Tap the orb, speak, then pause or tap again.'));
          return;
        }
        const ext = blob.type.includes('mp4') ? 'm4a' : 'webm';
        resolveFile(new File([blob], `jarvis-turn.${ext}`, { type: blob.type }));
      }
    } catch (error) {
      settled = true;
      cleanupAudio();
      rejectFile(error instanceof Error ? error : new Error('Could not finish the recording.'));
    }
  };

  const tick = (now: number) => {
    const dt = Math.max(0, now - lastTick);
    lastTick = now;
    try {
      if (audioContext.state === 'suspended') void audioContext.resume();
    } catch { /* ignore */ }
    analyser.getByteTimeDomainData(data);
    let sum = 0;
    for (let i = 0; i < data.length; i += 1) {
      const v = (data[i] - 128) / 128;
      sum += v * v;
    }
    const rms = Math.sqrt(sum / data.length);
    options?.onLevel?.(Math.min(1, 0.08 + rms * 8));
    if (rms > speechThreshold) {
      if (!heardSpeech) speechStartedAt = now;
      heardSpeech = true;
      silentFor = 0;
    } else if (heardSpeech) {
      silentFor += dt;
      // Only auto-end after real speech + a clear pause. Never end while the user
      // is still gathering their thoughts before speaking (that was cutting calls short).
      const spokenFor = speechStartedAt ? now - speechStartedAt : 0;
      if (spokenFor >= minMs && silentFor >= silenceMs) finish();
    }
    raf = requestAnimationFrame(tick);
  };

  recorder.ondataavailable = (event) => {
    if (event.data.size) chunks.push(event.data);
  };
  recorder.onerror = () => {
    if (settled) return;
    settled = true;
    cleanupAudio();
    rejectFile(new Error('Microphone recording failed.'));
  };
  recorder.onstop = () => {
    if (settled) return;
    settled = true;
    cleanupAudio();
    const blob = new Blob(chunks, { type: recorder.mimeType || 'audio/webm' });
    if (!blob.size) {
      rejectFile(new Error('No audio was captured. Tap the orb, speak clearly, then pause or tap again.'));
      return;
    }
    const ext = blob.type.includes('mp4') ? 'm4a' : blob.type.includes('wav') ? 'wav' : 'webm';
    resolveFile(new File([blob], `jarvis-turn.${ext}`, { type: blob.type || 'audio/webm' }));
  };

  recorder.start(120);
  raf = requestAnimationFrame(tick);
  const maxTimer = window.setTimeout(finish, maxMs);

  return {
    promise: promise.finally(() => window.clearTimeout(maxTimer)),
    stop: finish,
  };
}

export async function playAudioBlob(blob: Blob, volume = 1, signal?: AbortSignal): Promise<void> {
  const url = URL.createObjectURL(blob);
  const player = new Audio(url);
  player.volume = Math.max(0, Math.min(1, volume));
  await new Promise<void>((resolve, reject) => {
    const cleanup = () => {
      player.onended = null;
      player.onerror = null;
      player.pause();
      URL.revokeObjectURL(url);
      signal?.removeEventListener('abort', onAbort);
    };
    const onAbort = () => {
      cleanup();
      resolve();
    };
    if (signal?.aborted) {
      cleanup();
      resolve();
      return;
    }
    signal?.addEventListener('abort', onAbort, { once: true });
    player.onended = () => {
      cleanup();
      resolve();
    };
    player.onerror = () => {
      cleanup();
      reject(new Error('Audio playback failed.'));
    };
    void player.play().catch((error) => {
      cleanup();
      reject(error instanceof Error ? error : new Error('Audio playback was blocked. Click the page once, then try again.'));
    });
  });
}

/** Fallback when server TTS is unavailable — uses the browser voice engine. */
export function speakWithBrowser(text: string, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (!('speechSynthesis' in window)) {
      reject(new Error('Speech playback is not available in this browser.'));
      return;
    }
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = 1.02;
    utterance.pitch = 1;
    const voices = window.speechSynthesis.getVoices();
    const english = voices.find((v) => /en(-|_|$)/i.test(v.lang) && /female|samantha|karen|moira|zira|google/i.test(v.name))
      || voices.find((v) => /en(-|_|$)/i.test(v.lang))
      || voices[0];
    if (english) utterance.voice = english;
    let watchdog = 0;
    const cleanup = () => {
      utterance.onend = null;
      utterance.onerror = null;
      if (watchdog) window.clearInterval(watchdog);
      signal?.removeEventListener('abort', onAbort);
    };
    const onAbort = () => {
      cleanup();
      window.speechSynthesis.cancel();
      resolve();
    };
    if (signal?.aborted) {
      resolve();
      return;
    }
    signal?.addEventListener('abort', onAbort, { once: true });
    utterance.onend = () => {
      cleanup();
      resolve();
    };
    utterance.onerror = () => {
      cleanup();
      reject(new Error('Browser speech playback failed.'));
    };
    // Chrome/Electron often pauses speechSynthesis until resume() is called.
    watchdog = window.setInterval(() => {
      try { window.speechSynthesis.resume(); } catch { /* ignore */ }
    }, 250);
    window.speechSynthesis.speak(utterance);
    try { window.speechSynthesis.resume(); } catch { /* ignore */ }
  });
}
