import { useEffect, useMemo, useRef, type ReactNode } from "react";
import {
  ActionBarPrimitive,
  AssistantRuntimeProvider,
  BranchPickerPrimitive,
  AuiIf,
  ComposerPrimitive,
  ErrorPrimitive,
  MessagePartPrimitive,
  MessagePrimitive,
  ThreadPrimitive,
  useLocalRuntime,
} from "@assistant-ui/react";
import {
  ArrowClockwiseIcon,
  ArrowDownIcon,
  ArrowUpIcon,
  ArrowUpRightIcon,
  BrainIcon,
  CaretLeftIcon,
  CaretRightIcon,
  CircleNotchIcon,
  CheckIcon,
  ClockIcon,
  CoffeeIcon,
  CompassIcon,
  CopyIcon,
  FootprintsIcon,
  InfoIcon,
  MapPinIcon,
  MicrophoneIcon,
  PencilSimpleIcon,
  PlusIcon,
  SparkleIcon,
  StopIcon,
  TreeIcon,
} from "@phosphor-icons/react";
import { createRecommendationAdapter, samePlanningOrigin } from "./agent/recommendation-adapter";
import { restoreResultSelection } from "./agent/result-selection";
import type { Language, Place, Recommendation } from "@/types";
import "@/styles/assistant.css";

export interface AgentPanelProps {
  language: Language;
  context: Record<string, unknown>;
  onResult: (result: Recommendation, requestContext?: Record<string, unknown>) => void;
  onBusyChange?: (busy: boolean) => void;
  onPlaceSelect?: (id: string, restoring?: Recommendation) => void;
  onVoice?: () => void;
  onMemory?: () => void;
  remember?: boolean;
  renderGenerativeUI?: (result: Recommendation, routedResult: Recommendation, onSelectPlace: (id: string) => void) => ReactNode;
  className?: string;
  prompt?: { id: string; text: string };
  onQuery?: (text: string) => void;
  routedPlan?: {
    original: Recommendation;
    totalMinutes: number;
    walkingMinutes: number;
    distance: number;
    stops: { id: string; walkMinutes: number; distance: number }[];
    warnings: string[];
    limitations: string;
  };
}

function routePresentation(result: Recommendation, routed?: AgentPanelProps["routedPlan"]): Recommendation {
  if (!routed) return result;
  const signature = (plan: Recommendation) => JSON.stringify({
    coordinates: plan.route.coordinates,
    stops: plan.recommendations.map(p => [p.id, p.visit_minutes]),
    starts: plan.context.starts_at,
  });
  if (signature(result) !== signature(routed.original)) return result;
  return {
    ...result,
    route: { ...result.route, total_minutes: routed.totalMinutes, walk_minutes: routed.walkingMinutes,
      distance_m: routed.distance, estimated: false, warning: routed.limitations },
    recommendations: result.recommendations.map(place => {
      const stop = routed.stops.find(candidate => candidate.id === place.id);
      if (!stop) return place;
      return { ...place, walk_minutes: stop.walkMinutes, leg_distance_m: stop.distance,
        why: place.why
          .replace(/About \d+ minutes from the previous stop/, "About " + stop.walkMinutes + " minutes from the previous stop")
          .replace(/Около \d+ мин от предыдущей точки/, "Около " + stop.walkMinutes + " мин от предыдущей точки")
          .replace(/Алдыңғы орыннан шамамен \d+ минут/, "Алдыңғы орыннан шамамен " + stop.walkMinutes + " минут") };
    }),
    context: { ...result.context, missing_data: [
      ...(Array.isArray(result.context.missing_data) ? result.context.missing_data : []), ...routed.warnings,
    ] },
  };
}

const words = {
  en: {
    assistant: "Assistant", welcome: "Where shall we go?",
    starters: ["Coffee and a socket nearby", "A quiet 30-minute walk", "Something to do with children"],
    placeholder: "Ask about places, or refine your plan…", voice: "Voice", send: "Send message",
    cancel: "Stop response", planning: "Searching nearby places…", plan: "Walking route", stops: "stops",
    minute: "min", walking: "walking", visit: "here", source: "Source", details: "Sources & route details",
    unavailable: "No stops fit. Try more time or another starting point.", retry: "Regenerate", copy: "Copy response",
    latest: "Jump to latest message", map: "Show on map", estimated: "Estimated route",
    newChat: "New chat", edit: "Edit message", saveEdit: "Save & send", cancelEdit: "Cancel edit",
    previous: "Previous version", next: "Next version", versions: "Response versions", refine: "Refine your plan",
    memoryOn: "Memory on", memoryOff: "Memory off", memory: "Manage memory",
    stopped: "Response stopped.", emptyChat: "New chat started.", shortcuts: "Enter to send. Shift+Enter for a new line. Escape stops a response.",
    stages: { retrieve: "Searching nearby places…", rank: "Matching your preferences…", validate: "Checking time and access…", compose: "Preparing your plan…" },
  },
  ru: {
    assistant: "Ассистент", welcome: "Куда пойдём?",
    starters: ["Кофе и розетка рядом", "Тихая прогулка на 30 минут", "Куда сходить с ребёнком"],
    placeholder: "Спросите о местах или уточните план…", voice: "Голос", send: "Отправить сообщение",
    cancel: "Остановить ответ", planning: "Ищу места поблизости…", plan: "Пеший маршрут", stops: "места",
    minute: "мин", walking: "пешком", visit: "на месте", source: "Источник", details: "Источники и детали маршрута",
    unavailable: "Подходящих мест нет. Добавьте времени или смените отправную точку.", retry: "Новый вариант", copy: "Скопировать ответ",
    latest: "К последнему сообщению", map: "Показать на карте", estimated: "Приблизительный маршрут",
    newChat: "Новый чат", edit: "Изменить сообщение", saveEdit: "Сохранить и отправить", cancelEdit: "Отменить изменение",
    previous: "Предыдущий вариант", next: "Следующий вариант", versions: "Варианты ответа", refine: "Уточнить план",
    memoryOn: "Память вкл.", memoryOff: "Память выкл.", memory: "Управление памятью",
    stopped: "Ответ остановлен.", emptyChat: "Новый чат начат.", shortcuts: "Enter — отправить. Shift+Enter — новая строка. Escape — остановить ответ.",
    stages: { retrieve: "Ищу места поблизости…", rank: "Учитываю предпочтения…", validate: "Проверяю время и доступность…", compose: "Составляю план…" },
  },
  kk: {
    assistant: "Көмекші", welcome: "Қайда барамыз?",
    starters: ["Жақын жерде кофе мен розетка", "30 минуттық тыныш серуен", "Баламен қайда баруға болады"],
    placeholder: "Орын сұраңыз немесе жоспарды нақтылаңыз…", voice: "Дауыс", send: "Хабарлама жіберу",
    cancel: "Жауапты тоқтату", planning: "Жақын орындарды іздеп жатырмын…", plan: "Жаяу маршрут", stops: "орын",
    minute: "мин", walking: "жаяу", visit: "осында", source: "Дереккөз", details: "Дереккөздер мен маршрут мәліметтері",
    unavailable: "Сай келетін орын жоқ. Уақыт қосыңыз немесе бастапқы орынды өзгертіңіз.", retry: "Жаңа нұсқа", copy: "Жауапты көшіру",
    latest: "Соңғы хабарламаға өту", map: "Картадан көрсету", estimated: "Болжамды маршрут",
    newChat: "Жаңа чат", edit: "Хабарламаны өзгерту", saveEdit: "Сақтау және жіберу", cancelEdit: "Өзгертуді болдырмау",
    previous: "Алдыңғы нұсқа", next: "Келесі нұсқа", versions: "Жауап нұсқалары", refine: "Жоспарды нақтылау",
    memoryOn: "Жад қосулы", memoryOff: "Жад өшірулі", memory: "Жадты басқару",
    stopped: "Жауап тоқтатылды.", emptyChat: "Жаңа чат басталды.", shortcuts: "Enter — жіберу. Shift+Enter — жаңа жол. Escape — жауапты тоқтату.",
    stages: { retrieve: "Жақын орындарды іздеп жатырмын…", rank: "Қалауыңызға сәйкестендіремін…", validate: "Уақыт пен қолжетімділікті тексеремін…", compose: "Жоспарды дайындаймын…" },
  },
};

function sourceUrl(value: string) {
  try {
    const url = new URL(value);
    return url.protocol === "https:" || url.protocol === "http:" ? url.href : undefined;
  } catch {
    return undefined;
  }
}

function Stop({
  place,
  index,
  language,
  onPlaceSelect,
}: {
  place: Place;
  index: number;
  language: Language;
  onPlaceSelect?: (id: string) => void;
}) {
  const t = words[language];
  const source = sourceUrl(place.source.url);
  return (
    <li className="qa-stop">
      <span className="qa-stop-number" aria-hidden="true">{index + 1}</span>
      <div className="qa-stop-content">
        {onPlaceSelect ? (
          <button
            className="qa-stop-name"
            type="button"
            onClick={() => onPlaceSelect(place.id)}
            aria-label={`${t.map}: ${place.name}`}
          >
            <span>{place.name}</span><ArrowUpRightIcon size={15} />
          </button>
        ) : <h4 className="qa-stop-name">{place.name}</h4>}
        <p className="qa-stop-meta">
          <span><ClockIcon size={12} />{place.visit_minutes} {t.minute} {t.visit}</span>
          <span><FootprintsIcon size={12} />{place.walk_minutes} {t.minute} {t.walking}</span>
        </p>
        <p className="qa-stop-why">{place.why}</p>
        {place.action && <p className="qa-stop-action"><SparkleIcon size={13} />{place.action}</p>}
        {source && (
          <a className="qa-source" href={source} target="_blank" rel="noreferrer">
            {place.source.name}<ArrowUpRightIcon size={11} />
          </a>
        )}
      </div>
    </li>
  );
}

function RecommendationTool({
  result: originalResult,
  language,
  onPlaceSelect,
  routedPlan,
}: {
  result: Recommendation;
  language: Language;
  onPlaceSelect?: (id: string) => void;
  routedPlan?: AgentPanelProps["routedPlan"];
}) {
  const result = routePresentation(originalResult, routedPlan);
  const t = words[language];
  const caveats = [
    result.route.warning,
    ...(Array.isArray(result.context.missing_data)
      ? result.context.missing_data.filter((entry): entry is string => typeof entry === "string")
      : []),
  ].filter((entry): entry is string => Boolean(entry));
  const sources = result.recommendations.flatMap((place) =>
    [place.source, place.hours_source, place.description_source]
      .filter((source): source is NonNullable<typeof source> => Boolean(source))
      .filter((source) => sourceUrl(source.url)),
  ).filter((source, index, all) => all.findIndex((entry) => entry.url === source.url) === index);

  return (
    <section className="qa-plan" aria-label={t.plan}>
      <div className="qa-plan-heading">
        <span className="qa-plan-label"><MapPinIcon size={14} weight="duotone" />{t.plan}</span>
        {result.recommendations.length > 0 && <span className="qa-plan-duration">{result.route.total_minutes} {t.minute}</span>}
      </div>
      {result.recommendations.length > 0 ? (
        <>
          <p className="qa-plan-summary">
            {language === "ru" ? `Мест: ${result.recommendations.length}` : `${result.recommendations.length} ${t.stops}`}<span aria-hidden="true">·</span>
            {result.route.walk_minutes} {t.minute} {t.walking}
          </p>
          <ol className="qa-stops">
            {result.recommendations.map((place, index) => (
              <Stop key={place.id} place={place} index={index} language={language} onPlaceSelect={onPlaceSelect} />
            ))}
          </ol>
        </>
      ) : <p className="qa-no-stops">{t.unavailable}</p>}
      {(caveats.length > 0 || sources.length > 0) && (
        <details className="qa-evidence">
          <summary><InfoIcon size={13} />{t.details}</summary>
          <div className="qa-evidence-content">
            {result.route.estimated && <p className="qa-estimate">{t.estimated}</p>}
            {caveats.map((caveat, index) => <p key={index}>{caveat}</p>)}
            <div className="qa-evidence-links">
              {sources.map((source) => (
                <a href={sourceUrl(source.url)} key={source.url} target="_blank" rel="noreferrer">
                  {source.name}<ArrowUpRightIcon size={11} />
                </a>
              ))}
            </div>
          </div>
        </details>
      )}
    </section>
  );
}

function BranchPicker({ language }: { language: Language }) {
  const t = words[language];
  return (
    <BranchPickerPrimitive.Root className="qa-branches" hideWhenSingleBranch aria-label={t.versions}>
      <BranchPickerPrimitive.Previous className="qa-icon-button" aria-label={t.previous} title={t.previous}><CaretLeftIcon size={13} /></BranchPickerPrimitive.Previous>
      <span className="qa-branch-count"><BranchPickerPrimitive.Number /><span aria-hidden="true"> / </span><BranchPickerPrimitive.Count /></span>
      <BranchPickerPrimitive.Next className="qa-icon-button" aria-label={t.next} title={t.next}><CaretRightIcon size={13} /></BranchPickerPrimitive.Next>
    </BranchPickerPrimitive.Root>
  );
}

function EditComposer({ language }: { language: Language }) {
  const t = words[language];
  return (
    <ComposerPrimitive.Root className="qa-edit-composer" aria-label={t.edit}>
      <ComposerPrimitive.Input className="qa-composer-input" aria-label={t.edit} rows={2} maxRows={6} autoFocus addAttachmentOnPaste={false} />
      <div className="qa-edit-actions">
        <ComposerPrimitive.Cancel className="qa-text-button">{t.cancelEdit}</ComposerPrimitive.Cancel>
        <ComposerPrimitive.Send className="qa-edit-send">{t.saveEdit}<ArrowUpIcon size={14} /></ComposerPrimitive.Send>
      </div>
    </ComposerPrimitive.Root>
  );
}

function Refinements({ result, language }: { result: Recommendation; language: Language }) {
  const suggestions = result.followups?.filter((entry) => typeof entry === "string" && entry.trim()).slice(0, 3) ?? [];
  if (!suggestions.length) return null;
  return (
    <AuiIf condition={(state) => state.message.isLast && !state.thread.isRunning}>
      <div className="qa-refinements" role="group" aria-label={words[language].refine}>
        {suggestions.map((suggestion) => (
          <ThreadPrimitive.Suggestion key={suggestion} prompt={suggestion} send className="qa-refinement">
            {suggestion}<ArrowUpRightIcon size={12} />
          </ThreadPrimitive.Suggestion>
        ))}
      </div>
    </AuiIf>
  );
}

export function AgentPanel(props: AgentPanelProps) {
  const { language, onVoice, onMemory, remember, className, prompt } = props;
  const t = words[language];
  const latest = useRef(props);
  latest.current = props;
  const root = useRef<HTMLDivElement>(null);
  const lastApplied = useRef<string | null>(null);
  const adapter = useMemo(() => createRecommendationAdapter(() => ({
    ...latest.current,
    onResult: (result, requestContext) => {
      lastApplied.current = JSON.stringify(result);
      latest.current.onResult(result, requestContext);
    },
  })), []);
  const runtime = useLocalRuntime(adapter, { maxSteps: 1 });
  const sentPrompt = useRef<string | undefined>(undefined);

  useEffect(() => {
    let wasBusy: boolean | undefined;
    const update = () => {
      const state = runtime.thread.getState();
      if (state.isRunning !== wasBusy) {
        wasBusy = state.isRunning;
        latest.current.onBusyChange?.(state.isRunning);
      }
      if (state.isRunning) return;
      // Version navigation is an explicit choice of that plan's constraints.
      // It can restore filters, but cannot restore a different place/time/language.
      const answer = [...state.messages].reverse().find((message) => message.role === "assistant");
      const tool = answer?.content.find((part) => part.type === "tool-call" && part.toolName === "recommend_city_places" && part.result);
      if (tool?.type !== "tool-call" || !tool.result || JSON.stringify(tool.result) === lastApplied.current) return;
      const result = tool.result as Recommendation;
      if (!Array.isArray(result.recommendations) || !result.route) return;
      lastApplied.current = JSON.stringify(result);
      let requestContext: Record<string, unknown> | undefined;
      try {
        if (typeof tool.args.requestContext === "string") requestContext = JSON.parse(tool.args.requestContext);
      } catch { return; }
      if (!requestContext || !samePlanningOrigin(requestContext, latest.current.context)) return;
      if (typeof tool.args.message === "string") latest.current.onQuery?.(tool.args.message);
      latest.current.onResult(result, latest.current.context);
    };
    update();
    return runtime.thread.subscribe(update);
  }, [runtime]);

  useEffect(() => {
    if (!prompt || sentPrompt.current === prompt.id || !prompt.text.trim()) return;
    sentPrompt.current = prompt.id;
    runtime.thread.append(prompt.text);
  }, [prompt, runtime]);

  const newChat = () => {
    runtime.thread.reset();
    lastApplied.current = null;
    root.current?.querySelector<HTMLTextAreaElement>('.qa-footer textarea')?.focus();
  };

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <ThreadPrimitive.Root ref={root} className={`qa-assistant ${className ?? ""}`} aria-label={t.assistant}
        onKeyDownCapture={() => { if (root.current) root.current.dataset.keyboard = "true"; }}
        onPointerDownCapture={() => { if (root.current) delete root.current.dataset.keyboard; }}>
        <div className="qa-sessionbar">
          <h2>{t.assistant}</h2>
          <div className="qa-session-actions">
            {onMemory && <button type="button" className="qa-memory-button" onClick={onMemory} aria-label={`${t.memory}: ${remember ? t.memoryOn : t.memoryOff}`} aria-haspopup="dialog" title={t.memory}>
              <BrainIcon size={18} weight={remember ? "fill" : "regular"} />
            </button>}
            <AuiIf condition={(state) => !state.thread.isEmpty}>
              <AuiIf condition={(state) => !state.thread.isRunning}>
                <button type="button" className="qa-new-chat qa-icon-button" onClick={newChat} aria-label={t.newChat} title={t.newChat}><PlusIcon size={18} /></button>
              </AuiIf>
            </AuiIf>
          </div>
        </div>
        <ThreadPrimitive.Viewport className="qa-viewport" turnAnchor="bottom">
          <div className="qa-thread-body">
            <AuiIf condition={(state) => state.thread.isEmpty}>
              <div className="qa-welcome">
                <h3>{t.welcome}</h3>
                <div className="qa-starters">
                  {[CoffeeIcon, TreeIcon, CompassIcon].map((Icon, index) => (
                    <ThreadPrimitive.Suggestion key={index} prompt={t.starters[index]} send className="qa-starter">
                      <Icon size={18} /><span>{t.starters[index]}</span><ArrowUpRightIcon size={14} />
                    </ThreadPrimitive.Suggestion>
                  ))}
                </div>
              </div>
            </AuiIf>
            <ThreadPrimitive.Messages>
              {({ message }) => message.role === "user" ? message.composer.isEditing ? <EditComposer language={language} /> : (
                <MessagePrimitive.Root className="qa-user-row">
                  <div className="qa-user-message">
                    <MessagePrimitive.Parts>{({ part }) => part.type === "text" ? <p><MessagePartPrimitive.Text /></p> : null}</MessagePrimitive.Parts>
                  </div>
                  <ActionBarPrimitive.Root className="qa-user-actions" hideWhenRunning>
                    <ActionBarPrimitive.Edit className="qa-icon-button" aria-label={t.edit} title={t.edit}><PencilSimpleIcon size={14} /></ActionBarPrimitive.Edit>
                    <BranchPicker language={language} />
                  </ActionBarPrimitive.Root>
                </MessagePrimitive.Root>
              ) : message.role === "assistant" ? (
                <MessagePrimitive.Root className="qa-assistant-message" aria-label="Qala">
                  <div className="qa-message-byline"><SparkleIcon size={14} weight="fill" /><span>Qala</span></div>
                  <MessagePrimitive.Parts>
                    {({ part }) => {
                      if (part.type === "text") return <p className="qa-message-text"><MessagePartPrimitive.Text /></p>;
                      if (part.type !== "tool-call" || part.toolName !== "recommend_city_places") return null;
                      if (part.result) {
                        const result = part.result as Recommendation;
                        const routed = routePresentation(result, props.routedPlan);
                        const selectFromResult = (id: string) => {
                          if (!latest.current.onPlaceSelect) return;
                          restoreResultSelection({
                            result, placeId: id, requestContext: part.args.requestContext,
                            currentContext: latest.current.context, message: part.args.message,
                            cancelRunning: () => { if (runtime.thread.getState().isRunning) runtime.thread.cancelRun(); },
                            onQuery: (text) => latest.current.onQuery?.(text),
                            restore: (plan, captured) => {
                              lastApplied.current = JSON.stringify(plan);
                              latest.current.onResult(plan, captured);
                            },
                            select: (placeId, restoring) => latest.current.onPlaceSelect?.(placeId, restoring),
                          });
                        };
                        const generated = props.renderGenerativeUI?.(result, routed, selectFromResult);
                        return <>
                          {generated != null ? <div className="qa-generative">{generated}</div> : <RecommendationTool result={result} language={language} onPlaceSelect={props.onPlaceSelect ? selectFromResult : undefined} routedPlan={props.routedPlan} />}
                          {generated == null && <Refinements result={result} language={language} />}
                        </>;
                      }
                      const stage = typeof part.args.stage === "string" && part.args.stage in t.stages ? part.args.stage as keyof typeof t.stages : "retrieve";
                      return message.status.type === "running" ? <div className="qa-planning" role="status" aria-live="polite"><CircleNotchIcon className="qa-progress-spinner" size={17} /><span>{t.stages[stage]}</span></div> : null;
                    }}
                  </MessagePrimitive.Parts>
                  {message.status.type === "running" && message.content.length === 0 && <div className="qa-planning" role="status"><CircleNotchIcon className="qa-progress-spinner" size={17} />{t.planning}</div>}
                  {message.status.type === "incomplete" && message.status.reason === "cancelled" && <p className="qa-cancelled" role="status">{t.stopped}</p>}
                  <MessagePrimitive.Error><ErrorPrimitive.Root className="qa-error" role="alert"><InfoIcon size={16} /><ErrorPrimitive.Message /></ErrorPrimitive.Root></MessagePrimitive.Error>
                  <ActionBarPrimitive.Root className="qa-message-actions" hideWhenRunning>
                    <ActionBarPrimitive.Copy className="qa-icon-button" aria-label={t.copy} title={t.copy}>
                      <AuiIf condition={(state) => !state.message.isCopied}><CopyIcon size={15} /></AuiIf>
                      <AuiIf condition={(state) => state.message.isCopied}><CheckIcon size={15} /></AuiIf>
                    </ActionBarPrimitive.Copy>
                    <ActionBarPrimitive.Reload className="qa-retry" aria-label={t.retry} title={t.retry}><ArrowClockwiseIcon size={14} /><span>{t.retry}</span></ActionBarPrimitive.Reload>
                    <BranchPicker language={language} />
                  </ActionBarPrimitive.Root>
                </MessagePrimitive.Root>
              ) : null}
            </ThreadPrimitive.Messages>
          </div>
          <ThreadPrimitive.ViewportFooter className="qa-footer">
            <ThreadPrimitive.ScrollToBottom className="qa-scroll-bottom" aria-label={t.latest} title={t.latest}><ArrowDownIcon size={16} /></ThreadPrimitive.ScrollToBottom>
            <ComposerPrimitive.Root className="qa-composer">
              <span className="sr-only" id="qa-composer-shortcuts">{t.shortcuts}</span>
              <ComposerPrimitive.Input className="qa-composer-input" placeholder={t.placeholder} aria-label={t.placeholder} aria-describedby="qa-composer-shortcuts" rows={1} maxRows={5} autoFocus={false} addAttachmentOnPaste={false} unstable_insertNewlineOnTouchEnter />
              <div className="qa-composer-toolbar">
                {onVoice ? <button className="qa-voice-button" type="button" onClick={onVoice} aria-label={language === "en" ? "Talk to Qala" : t.voice}><MicrophoneIcon size={17} /><span>{t.voice}</span></button> : <span />}
                <AuiIf condition={(state) => !state.thread.isRunning}><ComposerPrimitive.Send className="qa-send-button" aria-label={t.send} title={t.send}><ArrowUpIcon size={19} weight="bold" /></ComposerPrimitive.Send></AuiIf>
                <AuiIf condition={(state) => state.thread.isRunning}><ComposerPrimitive.Cancel className="qa-send-button qa-cancel-button" aria-label={t.cancel} title={t.cancel}><StopIcon size={15} weight="fill" /></ComposerPrimitive.Cancel></AuiIf>
              </div>
            </ComposerPrimitive.Root>
          </ThreadPrimitive.ViewportFooter>
        </ThreadPrimitive.Viewport>
      </ThreadPrimitive.Root>
    </AssistantRuntimeProvider>
  );
}

export default AgentPanel;
