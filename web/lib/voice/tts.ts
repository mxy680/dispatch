let _primed = false;
let _lastSpokenAt = 0;

function _supported() {
  return typeof window !== "undefined" && "speechSynthesis" in window;
}

export function primeSpeechSynthesis() {
  if (!_supported()) return false;
  try {
    // Warm up voices list; some browsers populate asynchronously.
    window.speechSynthesis.getVoices();
    if (window.speechSynthesis.paused) window.speechSynthesis.resume();
    _primed = true;
    return true;
  } catch {
    return false;
  }
}

export function speak(text: string) {
  if (!_supported()) return false;
  const phrase = (text || "").trim();
  if (!phrase) return false;
  try {
    primeSpeechSynthesis();
    const now = Date.now();
    // Protect against rapid repeated calls cutting each other off.
    if (now - _lastSpokenAt < 250) {
      return false;
    }
    _lastSpokenAt = now;

    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(phrase);
    utterance.rate = 1;
    utterance.pitch = 1;
    utterance.volume = 1;
    window.speechSynthesis.speak(utterance);

    // Retry once if a browser drops the utterance before priming.
    if (!_primed) {
      setTimeout(() => {
        try {
          if (!window.speechSynthesis.speaking) {
            window.speechSynthesis.speak(new SpeechSynthesisUtterance(phrase));
          }
        } catch {
          // no-op
        }
      }, 120);
    }
    return true;
  } catch {
    return false;
  }
}

export function stopSpeaking() {
  if (!_supported()) return;
  window.speechSynthesis.cancel();
}
