/**
 * AudioWorkletProcessor — playback side of the call audio bridge.
 *
 * The main thread posts raw Int16 PCM (16 kHz mono S16LE, exactly what the
 * server relays from the other members) into this worklet via `port.postMessage`.
 * The processor buffers those samples and plays them out at the AudioContext's
 * sample rate (16 kHz), so each caller hears the others.
 */
class PCMPlayerProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this._buffer = new Float32Array(0);
    this.port.onmessage = (e) => {
      const i16 = new Int16Array(e.data);
      const f32 = new Float32Array(i16.length);
      for (let i = 0; i < i16.length; i++) {
        f32[i] = i16[i] / 32768;
      }
      const merged = new Float32Array(this._buffer.length + f32.length);
      merged.set(this._buffer);
      merged.set(f32, this._buffer.length);
      this._buffer = merged;
    };
  }

  process(_inputs, outputs) {
    const out = outputs[0][0];
    if (!out) return true;

    const need = out.length;
    if (this._buffer.length >= need) {
      out.set(this._buffer.subarray(0, need));
      this._buffer = this._buffer.subarray(need);
    } else {
      out.fill(0);
      if (this._buffer.length > 0) {
        out.set(this._buffer);
        this._buffer = new Float32Array(0);
      }
    }
    return true;
  }
}

registerProcessor('pcm-player', PCMPlayerProcessor);
