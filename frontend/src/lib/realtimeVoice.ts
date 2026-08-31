import { getAccessToken } from "./api";

export type RealtimeVoicePhase =
  | "idle"
  | "requesting_permission"
  | "connecting"
  | "listening"
  | "recognizing"
  | "generating"
  | "reply_ready"
  | "error";

export interface RealtimeVoiceMessage {
  type: string;
  turn_id?: string;
  transcript?: string;
  reply_text?: string;
  citation_ids?: string[];
  evidences?: Array<{
    evidence_id: string;
    source_title: string;
    article_ref: string;
    quote: string;
    effective_status: string;
  }>;
  coverage_status?: string;
  source?: string;
  confidence?: number;
  teacher_review_required?: boolean;
  message?: string;
  code?: string;
  recoverable?: boolean;
  audio?: {
    content_type: "audio/wav" | string;
    base64: string;
    size_bytes: number;
    sha256: string;
    duration_seconds: number;
    provider_sid_present: boolean;
    ai_generated_disclosure: true;
  };
  evidence_eligibility?: {
    learning_event_created: false;
    long_term_profile_eligible: false;
    formal_grading_eligible: false;
    human_review_required: true;
    reason: string;
  };
}

export class StreamingPcm16Resampler {
  private nextSourcePosition = 0;
  private totalSourceSamples = 0;
  private previousSample = 0;
  private hasPreviousSample = false;
  private readonly ratio: number;

  constructor(
    readonly sourceRate: number,
    readonly targetRate = 16000,
  ) {
    if (!(sourceRate > 0) || !(targetRate > 0)) {
      throw new Error("audio sample rates must be positive");
    }
    this.ratio = sourceRate / targetRate;
  }

  push(input: Float32Array): Int16Array {
    if (!input.length) return new Int16Array(0);
    const start = this.totalSourceSamples;
    const end = start + input.length - 1;
    const output: number[] = [];
    while (this.nextSourcePosition <= end) {
      const leftIndex = Math.floor(this.nextSourcePosition);
      const fraction = this.nextSourcePosition - leftIndex;
      const rightIndex = leftIndex + 1;
      if (fraction > 0 && rightIndex > end) break;
      let left: number;
      if (leftIndex === start - 1 && this.hasPreviousSample) left = this.previousSample;
      else if (leftIndex >= start && leftIndex <= end) left = input[leftIndex - start];
      else break;
      let value = left;
      if (fraction > 0) {
        const right = rightIndex >= start && rightIndex <= end
          ? input[rightIndex - start]
          : this.previousSample;
        value = left + (right - left) * fraction;
      }
      const clamped = Math.max(-1, Math.min(1, value));
      output.push(clamped < 0 ? Math.round(clamped * 32768) : Math.round(clamped * 32767));
      this.nextSourcePosition += this.ratio;
    }
    this.totalSourceSamples += input.length;
    this.previousSample = input[input.length - 1];
    this.hasPreviousSample = true;
    return Int16Array.from(output);
  }
}

export class PcmFrameAccumulator {
  private pending: number[] = [];

  constructor(readonly frameSamples = 640) {
    if (!Number.isInteger(frameSamples) || frameSamples <= 0) {
      throw new Error("frameSamples must be a positive integer");
    }
  }

  push(samples: Int16Array): Int16Array[] {
    for (const sample of samples) this.pending.push(sample);
    const frames: Int16Array[] = [];
    while (this.pending.length >= this.frameSamples) {
      frames.push(Int16Array.from(this.pending.splice(0, this.frameSamples)));
    }
    return frames;
  }

  flush(): Int16Array | null {
    if (!this.pending.length) return null;
    const frame = Int16Array.from(this.pending);
    this.pending = [];
    return frame;
  }
}

function int16ToBase64(samples: Int16Array): string {
  const bytes = new Uint8Array(samples.buffer, samples.byteOffset, samples.byteLength);
  let binary = "";
  for (let index = 0; index < bytes.length; index += 0x4000) {
    binary += String.fromCharCode(...bytes.subarray(index, index + 0x4000));
  }
  return btoa(binary);
}

function voiceSocketUrl(): string {
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  return `${protocol}://${window.location.host}/ws/realtime-voice`;
}

function turnId(): string {
  return `voice-${Date.now()}-${Math.random().toString(16).slice(2, 10)}`;
}

export class RealtimeVoiceClient {
  private socket: WebSocket | null = null;
  private stream: MediaStream | null = null;
  private context: AudioContext | null = null;
  private source: MediaStreamAudioSourceNode | null = null;
  private worklet: AudioWorkletNode | null = null;
  private silentGain: GainNode | null = null;
  private resampler: StreamingPcm16Resampler | null = null;
  private frames: PcmFrameAccumulator | null = null;
  private activeTurnId = "";
  private sequence = 0;
  private capturing = false;
  private closed = false;
  private readyResolver: ((message: RealtimeVoiceMessage) => void) | null = null;
  private readyRejecter: ((reason: Error) => void) | null = null;

  constructor(
    private readonly onMessage: (message: RealtimeVoiceMessage) => void,
    private readonly onPhase: (phase: RealtimeVoicePhase) => void,
  ) {}

  private async ensureSocket(): Promise<WebSocket> {
    if (this.socket?.readyState === WebSocket.OPEN) return this.socket;
    const token = getAccessToken();
    if (!token) throw new Error("登录状态已失效，请重新登录后使用实时语音。");
    this.onPhase("connecting");
    const socket = new WebSocket(voiceSocketUrl(), ["simlaw-auth", token]);
    this.socket = socket;
    return new Promise<WebSocket>((resolve, reject) => {
      const timer = window.setTimeout(() => {
        reject(new Error("连接实时语音服务超时。"));
        socket.close();
      }, 12000);
      socket.onopen = () => {
        window.clearTimeout(timer);
        resolve(socket);
      };
      socket.onerror = () => {
        window.clearTimeout(timer);
        reject(new Error("无法连接实时语音服务。"));
      };
      socket.onmessage = (event) => this.handleServerMessage(event);
      socket.onclose = (event) => {
        this.socket = null;
        this.rejectReady(new Error(event.code === 4401 ? "实时语音鉴权失败。" : "实时语音连接已关闭。"));
        if (!this.closed && this.activeTurnId) this.onPhase("error");
      };
    });
  }

  private handleServerMessage(event: MessageEvent): void {
    let message: RealtimeVoiceMessage;
    try {
      message = JSON.parse(String(event.data)) as RealtimeVoiceMessage;
    } catch {
      this.onMessage({ type: "voice_error", code: "invalid_server_message", message: "实时语音服务返回了无效消息。" });
      this.onPhase("error");
      return;
    }
    if (message.type === "voice_session_ready" && message.turn_id === this.activeTurnId) {
      this.readyResolver?.(message);
      this.clearReadyPromise();
    }
    if (message.type === "voice_error") {
      const error = new Error(message.message || "实时语音处理失败。");
      this.rejectReady(error);
      void this.cleanupCapture();
      this.activeTurnId = "";
      this.onPhase("error");
    } else if (message.type === "voice_transcript_final") {
      this.onPhase("recognizing");
    } else if (message.type === "voice_reply_generating" || message.type === "voice_reply_text") {
      this.onPhase("generating");
    } else if (message.type === "voice_reply") {
      this.activeTurnId = "";
      this.onPhase("reply_ready");
    } else if (message.type === "voice_turn_cancelled") {
      this.activeTurnId = "";
      this.onPhase("idle");
    }
    this.onMessage(message);
  }

  private clearReadyPromise(): void {
    this.readyResolver = null;
    this.readyRejecter = null;
  }

  private rejectReady(reason: Error): void {
    this.readyRejecter?.(reason);
    this.clearReadyPromise();
  }

  private async prepareMicrophone(): Promise<void> {
    if (!navigator.mediaDevices?.getUserMedia) {
      throw new Error("当前浏览器不支持麦克风实时采集。");
    }
    this.onPhase("requesting_permission");
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
      video: false,
    });
    const context = new AudioContext({ sampleRate: 16000, latencyHint: "interactive" });
    this.context = context;
    await context.audioWorklet.addModule("/audio-worklets/pcm16-capture.js");
    this.source = context.createMediaStreamSource(this.stream);
    this.worklet = new AudioWorkletNode(context, "pcm16-capture", {
      numberOfInputs: 1,
      numberOfOutputs: 1,
      outputChannelCount: [1],
      channelCount: 1,
    });
    this.silentGain = context.createGain();
    this.silentGain.gain.value = 0;
    this.worklet.connect(this.silentGain).connect(context.destination);
    this.resampler = new StreamingPcm16Resampler(context.sampleRate, 16000);
    this.frames = new PcmFrameAccumulator(640);
    this.worklet.port.onmessage = (event: MessageEvent<Float32Array>) => {
      if (!this.capturing || !this.resampler || !this.frames) return;
      const pcm = this.resampler.push(new Float32Array(event.data));
      for (const frame of this.frames.push(pcm)) this.sendAudioFrame(frame);
    };
  }

  async startTurn(): Promise<string> {
    if (this.activeTurnId) throw new Error("上一轮实时语音尚未结束。");
    this.closed = false;
    try {
      await this.prepareMicrophone();
      const socket = await this.ensureSocket();
      const id = turnId();
      this.activeTurnId = id;
      this.sequence = 0;
      const ready = new Promise<RealtimeVoiceMessage>((resolve, reject) => {
        this.readyResolver = resolve;
        this.readyRejecter = reject;
      });
      socket.send(JSON.stringify({
        type: "voice_start",
        turn_id: id,
        sample_rate: 16000,
        encoding: "pcm_s16le",
        language: "zh_cn",
      }));
      const timeout = window.setTimeout(() => this.rejectReady(new Error("讯飞实时会话启动超时。")), 15000);
      await ready.finally(() => window.clearTimeout(timeout));
      this.source?.connect(this.worklet!);
      await this.context?.resume();
      this.capturing = true;
      this.onPhase("listening");
      return id;
    } catch (reason) {
      await this.cleanupCapture();
      this.activeTurnId = "";
      this.onPhase("error");
      throw reason;
    }
  }

  private sendAudioFrame(frame: Int16Array): void {
    if (!this.activeTurnId || this.socket?.readyState !== WebSocket.OPEN) return;
    this.socket.send(JSON.stringify({
      type: "voice_audio",
      turn_id: this.activeTurnId,
      seq: this.sequence++,
      audio: int16ToBase64(frame),
    }));
  }

  async stopTurn(): Promise<void> {
    if (!this.activeTurnId) return;
    this.capturing = false;
    this.source?.disconnect();
    const remainder = this.frames?.flush();
    if (remainder?.length) this.sendAudioFrame(remainder);
    await this.cleanupCapture();
    if (this.socket?.readyState !== WebSocket.OPEN) throw new Error("实时语音连接已断开。");
    this.socket.send(JSON.stringify({ type: "voice_stop", turn_id: this.activeTurnId }));
    this.onPhase("recognizing");
  }

  async cancelTurn(): Promise<void> {
    const id = this.activeTurnId;
    this.capturing = false;
    await this.cleanupCapture();
    if (id && this.socket?.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify({ type: "voice_cancel", turn_id: id }));
    }
    this.activeTurnId = "";
    this.onPhase("idle");
  }

  private async cleanupCapture(): Promise<void> {
    this.capturing = false;
    this.worklet?.port && (this.worklet.port.onmessage = null);
    try { this.source?.disconnect(); } catch { /* already disconnected */ }
    try { this.worklet?.disconnect(); } catch { /* already disconnected */ }
    try { this.silentGain?.disconnect(); } catch { /* already disconnected */ }
    for (const track of this.stream?.getTracks() ?? []) track.stop();
    if (this.context && this.context.state !== "closed") await this.context.close();
    this.stream = null;
    this.context = null;
    this.source = null;
    this.worklet = null;
    this.silentGain = null;
    this.resampler = null;
    this.frames = null;
  }

  async close(): Promise<void> {
    this.closed = true;
    await this.cancelTurn();
    this.socket?.close(1000);
    this.socket = null;
  }
}
