class Pcm16CaptureProcessor extends AudioWorkletProcessor {
  process(inputs, outputs) {
    const input = inputs[0] && inputs[0][0];
    if (input && input.length) {
      const copy = new Float32Array(input.length);
      copy.set(input);
      this.port.postMessage(copy, [copy.buffer]);
    }
    for (const output of outputs) {
      for (const channel of output) channel.fill(0);
    }
    return true;
  }
}

registerProcessor("pcm16-capture", Pcm16CaptureProcessor);
