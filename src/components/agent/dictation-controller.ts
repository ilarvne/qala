import { readApiJson } from "../../lib/api";
import type { Language } from "../../types";

export type DictationState = "idle" | "requesting" | "recording" | "transcribing";
export interface DictationCallbacks {
  active: () => boolean;
  onState: (state: DictationState) => void;
  onSeconds: (seconds: number) => void;
  onTranscript: (text: string) => void;
  onError: (error: "unsupported" | "permission" | "empty" | "large" | "failed", detail?: string) => void;
}
const MAX_BYTES = 8 * 1024 * 1024;
const MIME_TYPES = ["audio/webm;codecs=opus", "audio/ogg;codecs=opus", "audio/webm", "audio/mp4"];

/** Owns microphone tracks and the one bounded, cancellable transcription request. */
export class DictationController {
  private generation = 0;
  private stream?: MediaStream;
  private recorder?: MediaRecorder;
  private chunks: Blob[] = [];
  private bytes = 0;
  private timer?: ReturnType<typeof setTimeout>;
  private interval?: ReturnType<typeof setInterval>;
  private request?: AbortController;
  private state: DictationState = "idle";
  constructor(private readonly callbacks: DictationCallbacks) {}

  private emit(state: DictationState) {
    this.state = state;
    if (this.callbacks.active()) this.callbacks.onState(state);
  }
  private stopTracks() {
    this.stream?.getTracks().forEach((track) => track.stop());
    this.stream = undefined;
  }
  private clearTimers() {
    clearTimeout(this.timer);
    clearInterval(this.interval);
    this.timer = undefined;
    this.interval = undefined;
  }
  cancel() {
    this.generation++;
    this.clearTimers();
    this.request?.abort();
    this.request = undefined;
    const recorder = this.recorder;
    this.recorder = undefined;
    if (recorder) {
      recorder.ondataavailable = null;
      recorder.onstop = null;
      recorder.onerror = null;
      if (recorder.state !== "inactive") recorder.stop();
    }
    this.stopTracks();
    this.chunks = [];
    this.bytes = 0;
    this.emit("idle");
  }
  stop() {
    if (this.state !== "recording" || !this.recorder) return;
    this.clearTimers();
    this.emit("transcribing");
    if (this.recorder.state !== "inactive") this.recorder.stop();
    this.stopTracks();
  }
  async start(language: Language) {
    this.cancel();
    const generation = this.generation;
    const current = () => generation === this.generation && this.callbacks.active();
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      this.callbacks.onError("unsupported");
      return;
    }
    this.emit("requesting");
    this.callbacks.onSeconds(0);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (!current()) { stream.getTracks().forEach((track) => track.stop()); return; }
      this.stream = stream;
      const mimeType = MIME_TYPES.find((mime) => MediaRecorder.isTypeSupported(mime));
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      this.recorder = recorder;
      this.chunks = [];
      this.bytes = 0;
      recorder.ondataavailable = (event) => {
        if (!current() || !event.data.size) return;
        this.bytes += event.data.size;
        if (this.bytes > MAX_BYTES) {
          this.cancel();
          if (this.callbacks.active()) this.callbacks.onError("large");
          return;
        }
        this.chunks.push(event.data);
      };
      recorder.onerror = () => {
        if (!current()) return;
        this.cancel();
        this.callbacks.onError("failed");
      };
      recorder.onstop = () => {
        this.clearTimers();
        this.stopTracks();
        if (!current()) return;
        const audio = new Blob(this.chunks, { type: recorder.mimeType || mimeType || "audio/webm" });
        this.chunks = [];
        if (!audio.size) { this.emit("idle"); this.callbacks.onError("empty"); return; }
        this.emit("transcribing");
        void this.transcribe(audio, language, generation);
      };
      recorder.start(250);
      this.emit("recording");
      const started = Date.now();
      this.interval = setInterval(() => {
        if (current()) this.callbacks.onSeconds(Math.min(60, Math.floor((Date.now() - started) / 1000)));
      }, 1000);
      this.timer = setTimeout(() => this.stop(), 60_000);
    } catch (error) {
      if (!current()) return;
      this.cancel();
      this.callbacks.onError(error instanceof DOMException && ["NotAllowedError", "PermissionDeniedError"].includes(error.name) ? "permission" : "failed");
    }
  }
  private async transcribe(audio: Blob, language: Language, generation: number) {
    const controller = new AbortController();
    this.request = controller;
    const current = () => generation === this.generation && this.callbacks.active() && !controller.signal.aborted;
    try {
      const form = new FormData();
      const extension = /ogg/.test(audio.type) ? "ogg" : /mp4/.test(audio.type) ? "m4a" : "webm";
      form.append("file", audio, "dictation." + extension);
      form.append("language", language);
      const response = await fetch("/api/voice/transcribe", { method: "POST", body: form, signal: controller.signal });
      const data = await readApiJson<{ text?: unknown }>(response, "Speech transcription is unavailable. Try again.");
      if (!current()) return;
      const text = typeof data.text === "string" ? data.text.trim() : "";
      this.emit("idle");
      if (!text) { this.callbacks.onError("empty"); return; }
      this.callbacks.onTranscript(text);
    } catch (error) {
      if (!current()) return;
      this.emit("idle");
      this.callbacks.onError("failed", error instanceof Error ? error.message : undefined);
    } finally {
      if (this.request === controller) this.request = undefined;
    }
  }
}
