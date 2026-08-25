/**
 * AudioWorkletProcessor — downsample mic audio to 16 kHz mono and convert
 * Float32 → Int16 PCM, posting fixed-size chunks back to the main thread.
 *
 * The browser's AudioContext is created at 16 kHz where supported, so the
 * resample is a no-op there. On browsers that ignore the sampleRate hint,
 * `sampleRate` (the worklet's actual input rate) is higher and we downsample
 * with linear interpolation.
 */
class PCMDownsamplerProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this._buffer = new Float32Array(0);
    this._inRate = sampleRate;   // actual input sample rate (worklet global)
    this._outRate = 16000;       // target for the realtime STT backend
    this._chunkSamples = 640;    // 40 ms at 16 kHz
  }

  process(inputs) {
    const input = inputs[0];
    if (!input || input.length === 0) return true;
    const channel = input[0];
    if (!channel || channel.length === 0) return true;

    // Accumulate this render quantum.
    const combined = new Float32Array(this._buffer.length + channel.length);
    combined.set(this._buffer);
    combined.set(channel, this._buffer.length);
    this._buffer = combined;

    const ratio = this._inRate / this._outRate;

    // Emit as many complete output chunks as the buffer supports.
    while (this._buffer.length >= Math.ceil(this._chunkSamples * ratio)) {
      const out = new Int16Array(this._chunkSamples);
      for (let i = 0; i < this._chunkSamples; i++) {
        const pos = i * ratio;
        const idx = pos | 0;
        const frac = pos - idx;
        const a = this._buffer[idx] || 0;
        const b = this._buffer[idx + 1] || a;
        let s = a + (b - a) * frac;
        if (s > 1) s = 1;
        else if (s < -1) s = -1;
        out[i] = (s * 32767) | 0;
      }
      // Transfer the ArrayBuffer so the main thread can send it straight over
      // the WebSocket without an extra copy.
      this.port.postMessage(out.buffer, [out.buffer]);

      const consumed = Math.floor(this._chunkSamples * ratio);
      this._buffer = this._buffer.slice(consumed);
    }
    return true;
  }
}

registerProcessor('pcm-downsampler', PCMDownsamplerProcessor);
