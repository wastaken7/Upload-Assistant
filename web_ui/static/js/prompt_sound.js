// Prepare audio during the Execute click; play only on a server sound event.
(() => {
  let audioContext = null;

  const unlock = () => {
    try {
      const AudioContext = window.AudioContext || window.webkitAudioContext;
      if (!AudioContext) return;
      if (!audioContext || audioContext.state === "closed") {
        audioContext = new AudioContext();
      }
      if (audioContext.state !== "running") {
        // Never delay an upload while waiting for browser audio permission.
        audioContext.resume().catch(() => {});
      }
    } catch {
      // Sound is optional; unavailable audio must not prevent execution.
    }
  };

  const play = () => {
    // Do not queue sounds that could play later, after a prompt is answered.
    if (!audioContext || audioContext.state !== "running") return;
    try {
      const oscillator = audioContext.createOscillator();
      const gain = audioContext.createGain();
      const start = audioContext.currentTime;
      oscillator.type = "sine";
      oscillator.frequency.setValueAtTime(880, start);
      gain.gain.setValueAtTime(0, start);
      gain.gain.linearRampToValueAtTime(0.16, start + 0.01);
      gain.gain.exponentialRampToValueAtTime(0.0001, start + 0.55);
      oscillator.connect(gain);
      gain.connect(audioContext.destination);
      oscillator.onended = () => {
        oscillator.disconnect();
        gain.disconnect();
      };
      oscillator.start(start);
      oscillator.stop(start + 0.6);
    } catch {
      // A muted or unavailable audio device must not interrupt the stream.
    }
  };

  window.uaPromptSound = { unlock, play };
})();
