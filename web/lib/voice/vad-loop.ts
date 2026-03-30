// Define the missing Web Speech API interfaces
interface SpeechRecognitionAlternative {
  transcript: string;
  confidence: number;
}

interface SpeechRecognitionResult {
  readonly length: number;
  item(index: number): SpeechRecognitionAlternative;
  [index: number]: SpeechRecognitionAlternative;
  isFinal: boolean;
}

interface SpeechRecognitionResultList {
  readonly length: number;
  item(index: number): SpeechRecognitionResult;
  [index: number]: SpeechRecognitionResult;
}

interface SpeechRecognitionEvent extends Event {
  readonly resultIndex: number;
  readonly results: SpeechRecognitionResultList;
}

interface SpeechRecognition extends EventTarget {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  start(): void;
  stop(): void;
  abort(): void;
  onstart: ((this: SpeechRecognition, ev: Event) => any) | null;
  onend: ((this: SpeechRecognition, ev: Event) => any) | null;
  onerror: ((this: SpeechRecognition, ev: Event) => any) | null;
  onresult: ((this: SpeechRecognition, ev: SpeechRecognitionEvent) => any) | null;
}

type SpeechRecognitionCtor = new () => SpeechRecognition;

declare global {
  interface Window {
    webkitSpeechRecognition?: SpeechRecognitionCtor;
    SpeechRecognition?: SpeechRecognitionCtor;
  }
}

export type VadLoop = {
  start: () => void;
  stop: () => void;
};

export function createVadLoop(opts: {
  onTranscript: (text: string) => void;
  onListeningChange?: (isListening: boolean) => void;
  onError?: (message: string) => void;
}): VadLoop {
  const Ctor = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!Ctor) {
    return {
      start: () => opts.onError?.("Speech recognition is not supported in this browser."),
      stop: () => {},
    };
  }

  const rec = new Ctor();
  rec.continuous = true;
  rec.interimResults = false;
  rec.lang = "en-US";

  rec.onstart = () => opts.onListeningChange?.(true);
  rec.onend = () => opts.onListeningChange?.(false);
  rec.onerror = (e: Event) => {
    // Cast appropriately since we're handling standard and webkit variants
    const msg = (e as unknown as { error?: string }).error ?? "voice error";
    opts.onError?.(msg);
  };
  rec.onresult = (event: SpeechRecognitionEvent) => {
    const results = event.results;
    const last = results[results.length - 1];
    const text = last?.[0]?.transcript?.trim();
    if (text) opts.onTranscript(text);
  };

  return {
    start: () => rec.start(),
    stop: () => rec.stop(),
  };
}