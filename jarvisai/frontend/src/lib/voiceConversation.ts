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
  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
    stream.getTracks().forEach((track) => track.stop());
  } catch (error) {
    const name = error instanceof DOMException ? error.name : '';
    if (name === 'NotAllowedError' || name === 'PermissionDeniedError') {
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
      : undefined;
  const recorder = new MediaRecorder(deviceStream, preferred ? { mimeType: preferred } : undefined);
  const chunks: Blob[] = [];
  let settled = false;
  let resolveFile!: (file: File) => void;
  let rejectFile!: (error: Error) => void;
  const promise = new Promise<File>((resolve, reject) => {
    resolveFile = resolve;
    rejectFile = reject;
  });

  const audioContext = new AudioContext();
  const source = audioContext.createMediaStreamSource(deviceStream);
  const analyser = audioContext.createAnalyser();
  analyser.fftSize = 2048;
  source.connect(analyser);
  const data = new Uint8Array(analyser.fftSize);
  let heardSpeech = false;
  let silentFor = 0;
  let lastTick = performance.now();
  let raf = 0;
  const silenceMs = options?.silenceMs ?? 1600;
  const maxMs = options?.maxMs ?? 20_000;

  const cleanupAudio = () => {
    if (raf) cancelAnimationFrame(raf);
    source.disconnect();
    void audioContext.close().catch(() => undefined);
    deviceStream.getTracks().forEach((track) => track.stop());
  };

  const finish = () => {
    if (settled) return;
    if (recorder.state === 'recording') recorder.stop();
  };

  const tick = (now: number) => {
    const dt = now - lastTick;
    lastTick = now;
    analyser.getByteTimeDomainData(data);
    let sum = 0;
    for (let i = 0; i < data.length; i += 1) {
      const v = (data[i] - 128) / 128;
      sum += v * v;
    }
    const rms = Math.sqrt(sum / data.length);
    options?.onLevel?.(Math.min(1, rms * 4));
    if (rms > 0.028) {
      heardSpeech = true;
      silentFor = 0;
    } else if (heardSpeech) {
      silentFor += dt;
      if (silentFor >= silenceMs) finish();
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
      rejectFile(new Error('No audio was captured. Hold the mic and speak clearly, then release.'));
      return;
    }
    const ext = blob.type.includes('mp4') ? 'm4a' : 'webm';
    resolveFile(new File([blob], `jarvis-turn.${ext}`, { type: blob.type }));
  };

  recorder.start(200);
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
    const cleanup = () => {
      utterance.onend = null;
      utterance.onerror = null;
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
    window.speechSynthesis.speak(utterance);
  });
}
