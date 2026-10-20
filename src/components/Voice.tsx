import { useEffect, useRef, useState } from "react";
import { ConversationProvider, useConversation } from "@elevenlabs/react";
import { Microphone as Mic, MicrophoneSlash as MicOff, PhoneDisconnect as PhoneOff, Waveform as Radio, CircleNotch as LoaderCircle, Stop, X } from "@phosphor-icons/react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { readApiJson } from "@/lib/api";
import { isVoiceLanguage, voiceLanguages, type VoiceLanguage } from "@/lib/voice-languages";
import { DictationController, type DictationState } from "./agent/dictation-controller";
import type { Language, Recommendation } from "@/types";
import { voiceToolRecommendation } from "./agent/voice-tool-result";

const words = {
  en: { title: "Talk to Qala", modes: "Voice mode", conversation: "Conversation", dictate: "Dictate", conversationData: "ElevenLabs receives your audio and the selected planning context during a conversation.", dictateData: "AlemPlus receives this recording and language to return text to the same city planner.", start: "Start conversation", end: "End conversation", mute: "Mute", unmute: "Unmute", muted: "Unmute microphone", unmuted: "Mute microphone", startRecording: "Start recording", stop: "Stop & send", cancel: "Cancel", connecting: "Connecting…", requesting: "Waiting for microphone access…", recording: "Recording", transcribing: "Transcribing…", speaking: "Qala is speaking…", listening: "Listening…", ready: "Ready", unavailable: "Voice is unavailable. Try again.", unsupported: "Recording is unavailable in this browser.", permission: "Microphone access was denied. Allow it in browser settings and try again.", empty: "No speech was recognized. Record again.", large: "The recording is too large. Try a shorter message.", limit: "Recording stops after 60 seconds." },
  ru: { title: "Поговорить с Qala", modes: "Режим голоса", conversation: "Разговор", dictate: "Диктовка", conversationData: "Во время разговора ElevenLabs получает аудио и выбранные параметры прогулки.", dictateData: "AlemPlus получает эту запись и язык, чтобы передать распознанный текст городскому помощнику.", start: "Начать разговор", end: "Завершить разговор", mute: "Выключить микрофон", unmute: "Включить микрофон", muted: "Включить микрофон", unmuted: "Выключить микрофон", startRecording: "Начать запись", stop: "Остановить и отправить", cancel: "Отмена", connecting: "Подключение…", requesting: "Ожидаю доступ к микрофону…", recording: "Запись", transcribing: "Распознаю речь…", speaking: "Qala говорит…", listening: "Слушаю…", ready: "Готово", unavailable: "Голос недоступен. Попробуйте снова.", unsupported: "Запись недоступна в этом браузере.", permission: "Доступ к микрофону запрещён. Разрешите его в настройках браузера.", empty: "Речь не распознана. Запишите ещё раз.", large: "Запись слишком большая. Попробуйте более короткое сообщение.", limit: "Запись остановится через 60 секунд." },
  kk: { title: "Qala-мен сөйлесу", modes: "Дауыс режимі", conversation: "Әңгіме", dictate: "Диктовка", conversationData: "Әңгіме кезінде ElevenLabs аудио мен таңдалған серуен параметрлерін алады.", dictateData: "AlemPlus осы жазба мен тілді алып, танылған мәтінді қала көмекшісіне жібереді.", start: "Әңгімені бастау", end: "Әңгімені аяқтау", mute: "Микрофонды өшіру", unmute: "Микрофонды қосу", muted: "Микрофонды қосу", unmuted: "Микрофонды өшіру", startRecording: "Жазуды бастау", stop: "Тоқтату және жіберу", cancel: "Болдырмау", connecting: "Қосылуда…", requesting: "Микрофон рұқсатын күтемін…", recording: "Жазылуда", transcribing: "Сөйлеу танылуда…", speaking: "Qala сөйлеп жатыр…", listening: "Тыңдап жатырмын…", ready: "Дайын", unavailable: "Дауыс қолжетімсіз. Қайта көріңіз.", unsupported: "Бұл браузерде жазу қолжетімсіз.", permission: "Микрофонға рұқсат берілмеді. Браузер параметрлерінен рұқсат беріңіз.", empty: "Сөйлеу танылмады. Қайта жазыңыз.", large: "Жазба тым үлкен. Қысқа хабарлама жазып көріңіз.", limit: "Жазу 60 секундтан кейін тоқтайды." },
};
type Mode = "conversation" | "dictate";
interface VoiceProps { open: boolean; onOpenChange: (value: boolean) => void; language: Language; onTranscript: (text: string) => void; onDictation?: (text: string) => void; onRecommendation?: (result: Recommendation, context: Record<string, unknown>) => void; context: string }

function VoiceSession(props: VoiceProps) {
  const { open, onOpenChange, language, context } = props;
  const t = words[language];
  const [mode, setMode] = useState<Mode>("conversation");
  const [voiceLanguage, setVoiceLanguage] = useState<VoiceLanguage>(language);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [transcript, setTranscript] = useState("");
  const [recording, setRecording] = useState<DictationState>("idle");
  const [seconds, setSeconds] = useState(0);
  const activeRef = useRef(open);
  const mountedRef = useRef(false);
  const generationRef = useRef(0);
  const requestRef = useRef<AbortController | null>(null);
  const sessionContext = useRef(context);
  const latest = useRef(props);
  latest.current = props;
  const modeRef = useRef(mode);
  modeRef.current = mode;
  const dictation = useRef<DictationController | null>(null);
  if (!dictation.current) dictation.current = new DictationController({
    active: () => mountedRef.current && activeRef.current && modeRef.current === "dictate",
    onState: setRecording,
    onSeconds: setSeconds,
    onError: (reason, detail) => {
      const copy = words[latest.current.language];
      setError(reason === "failed" ? detail || copy.unavailable : copy[reason]);
    },
    onTranscript: (text) => {
      setTranscript(text);
      (latest.current.onDictation ?? latest.current.onTranscript)(text);
      latest.current.onOpenChange(false);
    },
  });
  const conversation = useConversation({
    onMessage: (message) => {
      if (!activeRef.current || !mountedRef.current || modeRef.current !== "conversation") return;
      setTranscript(message.message);
      if (message.source === "user") latest.current.onTranscript(message.message);
    },
    onAgentToolResponse: (event) => {
      if (!activeRef.current || !mountedRef.current || modeRef.current !== "conversation") return;
      const accepted = voiceToolRecommendation(event, sessionContext.current, latest.current.context);
      if (!accepted) return;
      latest.current.onRecommendation?.(accepted.result, accepted.context);
      sessionContext.current = accepted.nextContext;
    },
    onError: (message) => {
      if (!activeRef.current || !mountedRef.current || modeRef.current !== "conversation") return;
      setBusy(false); setError(String(message) || words[latest.current.language].unavailable);
    },
    onConnect: () => {
      if (!activeRef.current || !mountedRef.current || modeRef.current !== "conversation") { void conversation.endSession(); return; }
      setBusy(false);
    },
    onDisconnect: () => { if (mountedRef.current) setBusy(false); },
  });
  const endSession = conversation.endSession;
  useEffect(() => {
    mountedRef.current = true;
    activeRef.current = open;
    return () => {
      mountedRef.current = false; activeRef.current = false;
      generationRef.current++; requestRef.current?.abort(); dictation.current?.cancel(); void endSession();
    };
  }, [endSession, open]);
  const close = () => {
    activeRef.current = false; generationRef.current++;
    requestRef.current?.abort(); dictation.current?.cancel(); void endSession(); setBusy(false); setRecording("idle");
  };
  const changeMode = (next: Mode) => {
    if (next === mode) return;
    generationRef.current++; requestRef.current?.abort(); dictation.current?.cancel(); void endSession();
    setBusy(false); setRecording("idle"); setError(""); setTranscript(""); setMode(next); modeRef.current = next;
    activeRef.current = open;
  };
  async function start() {
    const generation = ++generationRef.current;
    activeRef.current = true; sessionContext.current = context; setBusy(true); setError(""); requestRef.current?.abort();
    const controller = new AbortController(); requestRef.current = controller;
    const current = () => mountedRef.current && activeRef.current && modeRef.current === "conversation" && generation === generationRef.current;
    try {
      const response = await fetch("/api/voice/session", { method: "POST", signal: controller.signal, headers: { "Content-Type": "application/json" }, body: JSON.stringify({ language: voiceLanguage }) });
      const session = await readApiJson<{ signed_url?: string; conversation_token?: string }>(response, t.unavailable);
      if (!current()) return;
      if (!session.signed_url && !session.conversation_token) throw new Error(t.unavailable);
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      stream.getTracks().forEach((track) => track.stop());
      if (!current()) return;
      await conversation.startSession({ ...(session.signed_url ? { signedUrl: session.signed_url, connectionType: "websocket" as const } : { conversationToken: session.conversation_token }), dynamicVariables: { language: voiceLanguage, planner_language: language, context }, overrides: { agent: { language: voiceLanguage } } });
      if (!current()) void endSession();
    } catch (reason) {
      if (!current() || (reason instanceof DOMException && reason.name === "AbortError")) return;
      setError(reason instanceof Error ? reason.message : t.unavailable); setBusy(false); void endSession();
    }
  }
  const connected = conversation.status === "connected";
  const isRecording = mode === "dictate" && recording === "recording";
  const dictationBusy = mode === "dictate" && ["requesting", "transcribing"].includes(recording);
  const status = mode === "dictate" ? recording === "requesting" ? t.requesting : recording === "transcribing" ? t.transcribing : isRecording ? `${t.recording} · ${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}` : t.ready : connected ? conversation.isSpeaking ? t.speaking : t.listening : busy ? t.connecting : t.ready;
  return <Dialog open={open} onOpenChange={(value) => { if (!value) close(); onOpenChange(value); }}>
    <DialogContent className="voice-dialog">
      <DialogHeader><DialogTitle>{t.title}</DialogTitle><DialogDescription>{mode === "conversation" ? t.conversationData : t.dictateData}</DialogDescription></DialogHeader>
      <div role="group" aria-label={t.modes} className="flex justify-center gap-2">
        <Button variant={mode === "conversation" ? "default" : "outline"} aria-pressed={mode === "conversation"} onClick={() => changeMode("conversation")}>{t.conversation}</Button>
        <Button variant={mode === "dictate" ? "default" : "outline"} aria-pressed={mode === "dictate"} onClick={() => changeMode("dictate")}>{t.dictate}</Button>
      </div>
      {mode === "conversation" && <div className="grid gap-2 text-left">
        <label htmlFor="voice-language" className="text-sm font-medium">{language === "ru" ? "Язык разговора" : language === "kk" ? "Әңгіме тілі" : "Conversation language"}</label>
        <Select value={voiceLanguage} disabled={busy || connected} onValueChange={value => { if (isVoiceLanguage(value)) { setVoiceLanguage(value); setError(""); setTranscript(""); } }}>
          <SelectTrigger id="voice-language" className="w-full min-h-11"><SelectValue /></SelectTrigger>
          <SelectContent><SelectGroup>{voiceLanguages.map(item => <SelectItem key={item.code} value={item.code}><span lang={item.code} dir="auto">{item.name}</span></SelectItem>)}</SelectGroup></SelectContent>
        </Select>
      </div>}
      <div className={connected || isRecording ? "voice-orb is-connected" : "voice-orb"}>{mode === "dictate" ? <Mic /> : <Radio />}</div>
      <p className="voice-status" role="status" aria-live={isRecording ? "off" : "polite"}>{status}</p>
      {transcript && <p className="voice-transcript" dir="auto">{transcript}</p>}
      {error && <Alert variant="destructive"><AlertDescription>{error}</AlertDescription></Alert>}
      <div className="voice-actions">
        {mode === "dictate" ? <>
          {isRecording ? <Button onClick={() => dictation.current?.stop()} data-testid="dictation-stop"><Stop data-icon="inline-start" />{t.stop}</Button> : <Button onClick={() => { setError(""); setTranscript(""); activeRef.current = true; void dictation.current?.start(language); }} disabled={dictationBusy} data-testid="dictation-start">{dictationBusy ? <LoaderCircle className="spin" data-icon="inline-start" /> : <Mic data-icon="inline-start" />}{t.startRecording}</Button>}
          {(isRecording || dictationBusy) && <Button variant="outline" onClick={() => { dictation.current?.cancel(); setRecording("idle"); }}><X data-icon="inline-start" />{t.cancel}</Button>}
        </> : connected ? <>
          <Button variant="outline" aria-label={conversation.isMuted ? t.muted : t.unmuted} onClick={() => conversation.setMuted(!conversation.isMuted)}>{conversation.isMuted ? <MicOff data-icon="inline-start" /> : <Mic data-icon="inline-start" />}{conversation.isMuted ? t.unmute : t.mute}</Button>
          <Button onClick={close}><PhoneOff data-icon="inline-start" />{t.end}</Button>
        </> : <>
          <Button data-testid="voice-start" onClick={start} disabled={busy}>{busy ? <LoaderCircle className="spin" data-icon="inline-start" /> : <Mic data-icon="inline-start" />}{t.start}</Button>
          {busy && <Button variant="outline" onClick={close}>{t.cancel}</Button>}
        </>}
      </div>
      {mode === "dictate" && <span className="sr-only">{t.limit}</span>}
    </DialogContent>
  </Dialog>;
}
export default function Voice(props: VoiceProps) { return <ConversationProvider><VoiceSession {...props} /></ConversationProvider>; }
