/** Editable Russian Qala deck. Use the bundled Codex artifact-tool runtime.
 * Screenshot manifest: artifacts/presentation-assets/ru-screenshots.json.
 * Each value is a real captured image path, never a mocked UI render.
 */
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import { pathToFileURL } from 'node:url';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { createHash } from 'node:crypto';

const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
const assetDir = path.join(root, 'artifacts/presentation-assets');
const requiredScreenshots = ['walk', 'context', 'voice', 'memory', 'navigation', 'airport'];
const inputFiles = {
  screenshot_manifest: 'artifacts/presentation-assets/ru-screenshots.json',
  pitch_script: 'docs/pitch-script-ru.md', dataset_manifest: 'data/dataset-manifest.json',
  dataset: 'data/pois.json', backend_report: 'artifacts/backend-upgrade-verification.json',
  acceptance_report: 'artifacts/verification.json', conversation_report: 'artifacts/conversation-rag-evaluation.json',
  voice_languages: 'data/voice-languages.json',
  voice_configuration: 'artifacts/voice-language-configuration-verification.json',
  map_catalog_report: 'artifacts/map-catalog-verification.json',
};
const inputBytes = Object.fromEntries(await Promise.all(Object.entries(inputFiles).map(async ([key, file]) => [key, await fs.readFile(path.join(root, file))])));
const parse = key => JSON.parse(inputBytes[key].toString('utf8'));
const digest = bytes => createHash('sha256').update(bytes).digest('hex');
const sourceHashes = Object.fromEntries(Object.entries(inputFiles).map(([key, file]) => [file, digest(inputBytes[key])]));
const shots = parse('screenshot_manifest');
const script = inputBytes.pitch_script.toString('utf8');
const notes = script.split(/^## Слайд \d+\. /m).slice(1).map(s => s.split(/^## Соответствие/m)[0].trim());
if (notes.length !== 12) throw new Error('The Russian pitch must contain exactly twelve slide sections');
const pitchSpokenWords = notes.reduce((total, section) => total + section.split('\n').slice(1).join('\n').split('Источники:')[0].trim().split(/\s+/u).filter(Boolean).length, 0);
const proof = parse('backend_report');
const manifest = parse('dataset_manifest');
const dataset = parse('dataset');
const datasetSha256 = digest(inputBytes.dataset);
const datasetCount = manifest.metadata?.count;
if (!Number.isSafeInteger(datasetCount) || datasetCount < 1 || dataset.pois?.length !== datasetCount || dataset.metadata?.count !== datasetCount) {
  throw new Error('Published dataset and manifest POI counts disagree');
}
const inventoryFile = manifest.files?.find(file => file.path === 'data/pois.json');
if (!inventoryFile || inventoryFile.sha256 !== datasetSha256 || inventoryFile.bytes !== inputBytes.dataset.length) {
  throw new Error('Published inventory does not match its dataset manifest');
}
const backendTestCount = proof.backend_suite?.passed;
if (!Number.isSafeInteger(backendTestCount) || backendTestCount < 1 || proof.backend_suite.failed !== 0 || (proof.backend_suite.errors ?? 0) !== 0) {
  throw new Error('A successful current full backend report is required');
}
if (proof.method?.final_frozen_run !== true) {
  throw new Error('Backend inputs changed during verification; wait for a successful frozen-source run');
}
if (proof.dataset_sha256 !== datasetSha256 || proof.dataset_count !== datasetCount) {
  throw new Error('Backend verification describes a different dataset; wait for the final source/data test freeze');
}
for (const [file, expectedSha256] of Object.entries(proof.source_sha256 ?? {})) {
  if (digest(await fs.readFile(path.join(root, file))) !== expectedSha256) {
    throw new Error(`Backend verification source changed after its frozen run: ${file}`);
  }
}
const acceptance = parse('acceptance_report'), conversation = parse('conversation_report');
for (const [name, report] of [['acceptance', acceptance], ['conversation', conversation]]) {
  if (!Number.isSafeInteger(report.passed) || !Number.isSafeInteger(report.total) || report.passed < 1 || report.passed !== report.total) {
    throw new Error(`A successful ${name} evaluation is required`);
  }
}
if (acceptance.dataset?.count !== datasetCount || conversation.dataset_sha256 !== datasetSha256) {
  throw new Error('Scenario and conversation reports must describe the current published dataset');
}
const voiceLanguages = parse('voice_languages');
if (!Array.isArray(voiceLanguages) || voiceLanguages.length !== 16
    || new Set(voiceLanguages.map(language => language.code)).size !== voiceLanguages.length
    || voiceLanguages.some(language => typeof language.name !== 'string' || !language.name)) {
  throw new Error('The sixteen conversation language presets must match their published catalogue');
}
const voiceConfiguration = parse('voice_configuration');
if (voiceConfiguration.managed_payload_matches !== true || voiceConfiguration.signed_url_issued !== true
    || voiceConfiguration.configured_language_count !== voiceLanguages.length
    || JSON.stringify([...voiceConfiguration.configured_languages].sort()) !== JSON.stringify(voiceLanguages.map(language => language.code).sort())
    || voiceConfiguration.source_sha256?.[inputFiles.voice_languages] !== sourceHashes[inputFiles.voice_languages]) {
  throw new Error('The voice language claim requires matching provider configuration read-back');
}
const mapCatalog = parse('map_catalog_report');
const visiblePoiCount = dataset.pois.filter(place => String(place.operating_status ?? '').trim().toLowerCase() !== 'closed').length;
if (mapCatalog.passed !== mapCatalog.total || mapCatalog.passed < 1
    || mapCatalog.evidence?.coverage?.exact !== true
    || mapCatalog.evidence.coverage.count !== visiblePoiCount
    || mapCatalog.evidence.coverage.unique !== visiblePoiCount) {
  throw new Error('The whole-catalogue map claim requires a matching successful production browser report');
}
const screenshotEvidence = {};
for (const key of requiredScreenshots) {
  const asset = typeof shots[key] === 'string' ? { path: shots[key] } : shots[key];
  if (!asset || typeof asset.path !== 'string') throw new Error(`Missing real Russian screenshot: ${key}`);
  if (asset.crop && (Object.values(asset.crop).some(value => !Number.isFinite(value) || value < 0 || value >= 1)
      || (asset.crop.left ?? 0) + (asset.crop.right ?? 0) >= 1 || (asset.crop.top ?? 0) + (asset.crop.bottom ?? 0) >= 1)) {
    throw new Error(`Invalid screenshot crop: ${key}`);
  }
  const filename = path.resolve(root, asset.path);
  const bytes = await fs.readFile(filename);
  screenshotEvidence[key] = { path: asset.path, sha256: digest(bytes), ...(asset.crop ? { crop: asset.crop } : {}) };
}
if (process.argv.includes('--check-inputs')) {
  console.log(JSON.stringify({ authoring_started: false, dataset_pois: datasetCount, dataset_sha256: datasetSha256,
    backend_tests_passed: backendTestCount, acceptance: { passed: acceptance.passed, total: acceptance.total },
    conversation: { passed: conversation.passed, total: conversation.total }, screenshots: screenshotEvidence }, null, 2));
  process.exit(0);
}
const runtime = process.env.QALA_RUNTIME_DIR || path.join(os.homedir(), '.cache/codex-runtimes/codex-primary-runtime');
const skill = path.join(os.homedir(), '.codex/plugins/cache/openai-primary-runtime/presentations/26.1015.12040/skills/presentations');
const modules = path.join(runtime, 'dependencies/node/node_modules');
process.env.RUNTIME_NODE_MODULES ||= modules;
const { Presentation, PresentationFile } = await import(pathToFileURL(path.join(modules, '@oai/artifact-tool/dist/artifact_tool.mjs')).href);
const { default: sharp } = await import(pathToFileURL(path.join(modules, 'sharp/dist/index.mjs')).href);
const { finalizePresentation } = await import(pathToFileURL(path.join(skill, 'container_tools/artifact_tool_utils.mjs')).href);
const React = await import(pathToFileURL(path.join(root, 'node_modules/react/index.js')).href);
const { renderToStaticMarkup } = await import(pathToFileURL(path.join(root, 'node_modules/react-dom/server.node.js')).href);
const icons = await import(pathToFileURL(path.join(root, 'node_modules/@phosphor-icons/react/dist/ssr/index.es.js')).href);
const build = path.join(root, '.presentation-build', `ru-${Date.now()}`);
await fs.mkdir(build, { recursive: true });
await fs.symlink(modules, path.join(build, 'node_modules'), 'dir');
const C = { white: '#FFFFFF', ink: '#1D2026', blue: '#3155EB', muted: '#606975', rule: '#DDE1E7', faint: '#F4F6F9' };
const deck = Presentation.create({ slideSize: { width: 1280, height: 720 } });
function russianCount(number, one, few, many) {
  return number % 100 >= 11 && number % 100 <= 14 ? many : number % 10 === 1 ? one : number % 10 >= 2 && number % 10 <= 4 ? few : many;
}

function text(s, value, x, y, w, h, size = 30, color = C.ink, bold = false) {
  const shape = s.shapes.add({ geometry: 'textbox', name: value.slice(0, 60), position: { left: x, top: y, width: w, height: h }, fill: 'none', line: { fill: 'none', width: 0 } });
  shape.text = value;
  shape.text.style = { typeface: 'Inter', fontSize: size, color, bold, wrap: 'square', autoFit: 'none', verticalAlignment: 'top', insets: 0 };
  return shape;
}
function slide(title, dark = false) {
  const s = deck.slides.add();
  s.background.fill = dark ? C.ink : C.white;
  if (title) text(s, title, 64, 48, 1152, 80, 48, dark ? C.white : C.ink, true);
  const index = deck.slides.items.length - 1;
  s.speakerNotes.text = notes[index] || '';
  return s;
}
async function image(s, filename, x, y, w, h, alt, fit = 'contain', crop) {
  const file = path.isAbsolute(filename) ? filename : path.join(root, filename);
  const bytes = await fs.readFile(file);
  const metadata = await sharp(bytes).metadata();
  const box = { left: Math.round(metadata.width * (crop?.left || 0)), top: Math.round(metadata.height * (crop?.top || 0)) };
  box.width = metadata.width - box.left - Math.round(metadata.width * (crop?.right || 0));
  box.height = metadata.height - box.top - Math.round(metadata.height * (crop?.bottom || 0));
  if (fit === 'cover') {
    if (box.width / box.height > w / h) {
      const width = Math.round(box.height * w / h);
      box.left += Math.round((box.width - width) / 2);
      box.width = width;
    } else {
      const height = Math.round(box.width * h / w);
      box.top += Math.round((box.height - height) / 2);
      box.height = height;
    }
  }
  // Avoid the renderer's crop+contain stretch: embed an exact lossless source
  // fragment in an aspect-preserving native frame. No text is reconstructed.
  const cropped = await sharp(bytes).extract(box).png().toBuffer();
  const scale = Math.min(w / box.width, h / box.height);
  const iw = box.width * scale, ih = box.height * scale;
  const processedDir = path.join(build, 'processed-assets');
  await fs.mkdir(processedDir, { recursive: true });
  await fs.writeFile(path.join(processedDir, path.parse(file).name + '.png'), cropped);
  s.images.add({ blob: cropped.buffer.slice(cropped.byteOffset, cropped.byteOffset + cropped.byteLength), contentType: 'image/png', alt, position: { left: x + (w - iw) / 2, top: y + (h - ih) / 2, width: iw, height: ih } });
}
async function screenshot(s, key, x, y, w, h) {
  if (!shots[key]) throw new Error(`Missing real Russian screenshot: ${key}`);
  const asset = typeof shots[key] === 'string' ? { path: shots[key] } : shots[key];
  await image(s, asset.path, x, y, w, h, `Работающее приложение Qala, русский интерфейс: ${key}`, asset.fit || 'contain', asset.crop);
  s.speakerNotes.append(`\nФактический экран приложения: ${asset.path}. Смоделированный публичный запрос и выбранная локация; личные данные не использовались.${asset.crop ? ' Для читаемости показан фрагмент экрана, без изменения содержимого.' : ''}`);
}
async function icon(s, name, x, y, size = 52, color = C.blue) {
  const component = icons[`${name}Icon`];
  if (!component) throw new Error(`Unknown official Phosphor icon ${name}`);
  const svg = renderToStaticMarkup(React.createElement(component, { size: 256, color, weight: 'regular' }));
  const iconDir = path.join(assetDir, 'phosphor');
  await fs.mkdir(iconDir, { recursive: true });
  await fs.writeFile(path.join(iconDir, `${name}.svg`), svg);
  s.images.add({ svg, alt: `Phosphor ${name}`, position: { left: x, top: y, width: size, height: size } });
  s.speakerNotes.append('\nИконки: официальный @phosphor-icons/react 2.1.10, MIT, https://github.com/phosphor-icons/react.');
}
function statement(s, heading, body, x, y, w, { dark = false, gap = 49, bodyHeight = 140 } = {}) {
  text(s, heading, x, y, w, 48, 29, dark ? C.white : C.ink, true);
  text(s, body, x, y + gap, w, bodyHeight, 27, dark ? '#CDD2DD' : C.muted);
}

// 1. One generated illustration, with an editable direct title.
{
  const s = slide('');
  await image(s, 'artifacts/presentation-assets/qala-cover-generated.png', 0, 0, 1280, 720, 'Концептуальная иллюстрация бумажного атласа; не точная карта Астаны', 'cover');
  text(s, 'Qala', 62, 214, 440, 150, 112, C.white, true);
  text(s, 'ИИ-помощник\nпо прогулкам\nв Астане', 68, 382, 420, 186, 40, C.white);
  text(s, 'Build with AI', 68, 650, 330, 36, 23, '#D1D5DC');
  s.speakerNotes.append('\nСгенерированная обложка: artifacts/presentation-assets/qala-cover-generated.png; описание docs/asset-prompts-presentation-ru.json. Не использовать как свидетельство картографической точности.');
}
// 2. Business hypothesis, not invented traction.
{
  const s = slide('Пользователь и бизнес-гипотеза');
  text(s, '«У меня есть час.\nЧто посмотреть\nрядом?»', 64, 190, 620, 250, 53, C.ink, true);
  text(s, 'Жители · гости города · семьи', 68, 503, 610, 48, 27, C.muted);
  statement(s, 'Пилот с партнёром', 'Отель или городской сервис\nкак канал знакомства\nс продуктом', 780, 190, 432);
  statement(s, 'Гипотеза монетизации', 'Обновление сведений\nи тематических подборок\nдля партнёров', 780, 422, 432);
  text(s, 'Спрос, цена и партнёрства\nпока не подтверждены', 68, 596, 620, 73, 26, C.muted);
}
// 3. Actual product evidence dominates the slide.
{
  const s = slide('');
  await screenshot(s, 'walk', 0, 0, 1280, 720);
  s.speakerNotes.append(`\nКарта действующего каталога: artifacts/map-catalog-verification.json. В обычном просмотре ${visiblePoiCount} уникальных мест из ${datasetCount} записей корпуса; закрытая история не показана. Нативные кластеры MapLibre, общий поиск и выбор карточки проверены на реальном production frontend.`);
}
// 4. All three remaining brief scenarios stay visible and concrete.
{
  const s = slide('Семья, вылет и ночь');
  await screenshot(s, 'airport', 650, 148, 566, 515);
  await icon(s, 'UsersThree', 64, 162, 48);
  statement(s, 'С ребёнком', 'Семейные места и размер группы', 132, 162, 493, { gap: 47, bodyHeight: 88 });
  await icon(s, 'AirplaneTakeoff', 64, 320, 48);
  statement(s, 'Два часа перед вылетом', 'Уточнение дороги + резерв 90 минут', 132, 320, 493, { gap: 47, bodyHeight: 88 });
  await icon(s, 'Moon', 64, 478, 48);
  statement(s, 'Ночная активность', 'Только подходящие известные часы', 132, 478, 493, { gap: 47, bodyHeight: 88 });
}
// 5. Distinct real UI state, no reconstructed chat components.
{
  const s = slide('Сравнение и уточнение плана');
  statement(s, 'Сравнить остановки', 'Время в пути, посещение\nи опубликованное расписание', 64, 202, 605);
  statement(s, 'Продолжить диалог', 'Сохранить контекст\nи изменить ограничения', 64, 436, 605);
  await screenshot(s, 'context', 704, 143, 512, 520);
}
// 6. The actual inventory and a licensed real venue photograph.
{
  const s = slide('Собранные данные Астаны');
  text(s, new Intl.NumberFormat('ru-RU').format(datasetCount).replaceAll('\u00a0', ' '), 64, 158, 630, 138, 105, C.blue, true);
  text(s, russianCount(datasetCount, 'точка интереса', 'точки интереса', 'точек интереса'), 70, 302, 580, 60, 34, C.ink);
  text(s, 'Автоматический сбор\nJSON · CSV · GeoJSON', 70, 395, 580, 95, 30, C.muted);
  await image(s, 'public/photos/1093b8681e36efe42444.jpg', 768, 163, 448, 376, 'Интерьер Национального музея Республики Казахстан — реальная фотография Davide Mauro, CC BY-SA 4.0', 'cover');
  text(s, 'Национальный музей', 768, 557, 440, 42, 25, C.ink, true);
  text(s, 'Davide Mauro · CC BY-SA 4.0', 768, 611, 440, 36, 21, C.muted);
  s.speakerNotes.append('\nФото: https://commons.wikimedia.org/wiki/File:National_Museum_of_the_Republic_of_Kazakhstan_01.jpg ; Davide Mauro ; CC BY-SA 4.0 https://creativecommons.org/licenses/by-sa/4.0 . Фото обрезано для композиции. Источник данных © OpenStreetMap contributors https://www.openstreetmap.org/copyright , ODbL.');
  s.speakerNotes.append(`\nИсточник каталога: data/dataset-manifest.json, ${datasetCount} POI. SHA-256 опубликованного data/pois.json: ${datasetSha256}.`);
}
// 7. Editable high-level diagram, as requested by the brief.
{
  const s = slide('Как работает RAG', true);
  const columns = [
    ['MapPin', 'Запрос и контекст', 'Место, интересы,\nвремя и ограничения'],
    ['Database', 'Поиск по POI', 'Текст + локальная нейросеть\n+ проверка условий'],
    ['CheckCircle', 'Проверенный план', 'Реальные места,\nобъяснения и действия'],
  ];
  for (const [i, [name, title, body]] of columns.entries()) {
    const x = 64 + i * 406;
    await icon(s, name, x, 210, 66, '#8FA7FF');
    text(s, title, x, 321, 355, 84, 34, C.white, true);
    text(s, body, x, 437, 355, 121, 27, '#CDD2DD');
    if (i < 2) await icon(s, 'ArrowRight', x + 332, 220, 42, '#8FA7FF');
  }
  text(s, 'Модель не добавляет места и факты вне найденных источников', 64, 629, 1152, 55, 28, C.white);
}
// 8. Real voice controls, separate from phone-call proof.
{
  const s = slide(`Голос на ${voiceLanguages.length} языках`);
  await screenshot(s, 'voice', 64, 145, 724, 513);
  await icon(s, 'Microphone', 842, 167, 57);
  statement(s, 'ElevenLabs', 'Выбор языка разговора\nТот же планировщик', 842, 249, 374);
  statement(s, 'AlemPlus', 'Диктовка EN / RU\nОтдельная модель KK', 842, 458, 374);
  s.speakerNotes.append('\nРеальный WebSocket-сеанс проверял синтетический текстовый вход и поток настоящего аудио, включая серверный вызов планировщика. Успешный телефонный звонок или микрофонный ввод этим не подтверждаются.');
  s.speakerNotes.append(`\nЯзыки разговора: ${voiceLanguages.map(language => `${language.name} (${language.code})`).join(', ')}. Источники: data/voice-languages.json и artifacts/voice-language-configuration-verification.json. Конфигурация применена и повторно прочитана у провайдера, подписанная сессия выдана без начала разговора. Планировщик поддерживает EN/RU/KK. Казахская локализация оболочки частичная, часть элементов отображается по-английски. Выбор языка разговора не означает шестнадцать проверенных живых звонков или независимую оценку произношения.`);
}
// 9. Street routing and honest accessibility scope.
{
  const s = slide('Маршрут и доступность');
  await screenshot(s, 'navigation', 64, 146, 640, 509);
  await icon(s, 'Path', 798, 165, 56);
  statement(s, 'Пешком', 'Инструкции\nЭкспорт GPX\nКарта 2D / 3D', 798, 249, 418);
  await icon(s, 'Wheelchair', 798, 447, 54);
  text(s, 'Доступность входа\nне гарантирует\nпуть без ступеней', 798, 527, 418, 136, 26, C.muted);
}
// 10. Inspection and deletion are visible product actions.
{
  const s = slide('Память и приватность');
  await screenshot(s, 'memory', 64, 144, 727, 513);
  await icon(s, 'ShieldCheck', 845, 163, 58);
  statement(s, 'По согласию', 'Просмотр, изменение\nи удаление настроек', 845, 249, 371);
  statement(s, '30 дней', 'Без переписки\nи точных координат\nв памяти предпочтений', 845, 456, 371);
}
// 11. Source-linked verification, with material limits on the same canvas.
{
  const s = slide('Проверки и ограничения');
  text(s, String(backendTestCount), 64, 176, 325, 115, 87, C.blue, true);
  text(s, russianCount(backendTestCount, 'автотест сервера', 'автотеста сервера', 'автотестов сервера'), 69, 307, 335, 50, 30, C.ink);
  text(s, `${acceptance.passed} / ${acceptance.total}`, 445, 176, 378, 115, 75, C.blue, true);
  text(s, 'сценарных проверок', 450, 307, 375, 50, 29, C.ink);
  text(s, `${conversation.passed} / ${conversation.total}`, 867, 176, 347, 115, 75, C.blue, true);
  text(s, 'проверок диалога', 872, 307, 341, 50, 29, C.ink);
  text(s, 'Часы не гарантируют вход\nДоступность улиц не проверена', 69, 433, 554, 125, 30, C.muted);
  text(s, 'Календарь одного оператора\nТелефонный звонок не проверен', 683, 433, 533, 125, 30, C.muted);
  s.speakerNotes.append(`\nИсточники чисел: artifacts/backend-upgrade-verification.json (${backendTestCount} успешных тестов, ${proof.backend_suite.seconds} с); artifacts/verification.json (${acceptance.passed}/${acceptance.total}); artifacts/conversation-rag-evaluation.json (${conversation.passed}/${conversation.total}). Каждый отчёт сохраняет свою дату и область проверки. Дополнительные сценарные оценки не становятся новым live-тестом при экспорте презентации.`);
}
// 12. A concrete pilot decision with hypotheses clearly identified.
{
  const s = slide('План пилота', true);
  text(s, 'Пилот с отелем\nили городским сервисом', 64, 180, 1100, 165, 57, C.white, true);
  statement(s, 'Пользовательская ценность', 'Выбор остановки · начало маршрута\nОценка полезности · повторное использование', 69, 402, 1115, { dark: true });
  text(s, 'Измерять нарушения ограничений, свежесть данных\nи стоимость завершённого плана', 69, 596, 1125, 86, 30, '#CDD2DD');
}

// Every slide is rendered, then the package is independently finalized.
for (const [index, s] of deck.slides.items.entries()) {
  const stem = `slide-${String(index + 1).padStart(2, '0')}`;
  await fs.writeFile(path.join(build, `${stem}.png`), new Uint8Array(await (await deck.export({ slide: s, format: 'png', scale: 1 })).arrayBuffer()));
  await fs.writeFile(path.join(build, `${stem}.layout.json`), await (await s.export({ format: 'layout' })).text());
}
await fs.writeFile(path.join(build, 'montage.webp'), new Uint8Array(await (await deck.export({ format: 'webp', montage: true })).arrayBuffer()));
const candidatePath = path.join(build, 'candidate.pptx');
await (await PresentationFile.exportPptx(deck)).save(candidatePath);
const finalPath = path.join(build, 'output/presentation-ru.pptx');
await fs.mkdir(path.dirname(finalPath), { recursive: true });
const validation = await finalizePresentation({
  workspaceDir: root, candidatePath, finalPath,
  pythonExecutable: path.join(runtime, 'dependencies/python/bin/python3'),
  integrityValidatorPath: path.join(skill, 'container_tools/inspect_presentation_package_integrity.py'),
  layoutValidatorPath: path.join(skill, 'container_tools/inspect_presentation_layout_geometry.py'),
  layoutArgs: ['--expected-slide-size-emu', '12192000,6858000', '--validate-bullet-geometry', '--validate-heading-fit'],
  explicitTotalSlideCount: 12,
  requiredNativeTableOwnerSlides: [], requiredNativeChartOwnerSlides: [],
  fontPolicy: { basis: 'design', families: ['Inter'] }, verifyArtifactToolImport: true,
  receiptPath: path.join(build, 'validation.json'),
});
const outputPptx = path.join(root, 'artifacts/presentation-ru.pptx');
await fs.copyFile(finalPath, outputPptx);
const run = promisify(execFile);
await run(path.join(runtime, 'dependencies/bin/override/soffice'), ['--headless', `-env:UserInstallation=${pathToFileURL(path.join(build, 'lo-profile')).href}`, '--convert-to', 'pdf:impress_pdf_Export', '--outdir', path.dirname(finalPath), finalPath], { timeout: 90000 });
await fs.copyFile(path.join(path.dirname(finalPath), 'presentation-ru.pdf'), path.join(root, 'artifacts/presentation-ru.pdf'));
await fs.writeFile(path.join(root, 'artifacts/presentation-ru-verification.json'), JSON.stringify({
  generated_at: new Date().toISOString(), slides: 12, language: 'ru', target_pitch_seconds: 360,
  pitch_spoken_words: pitchSpokenWords, build_directory: path.relative(root, build),
  editable_pptx: 'artifacts/presentation-ru.pptx', pdf: 'artifacts/presentation-ru.pdf',
  screenshot_manifest: inputFiles.screenshot_manifest, screenshot_evidence: screenshotEvidence,
  dataset_pois: datasetCount, map_visible_pois: visiblePoiCount, dataset_sha256: datasetSha256, backend_full_suite_reported: backendTestCount,
  conversation_languages: voiceLanguages.map(language => language.code),
  voice_claim_scope: 'Sixteen configured provider language presets, read back with a signed session. Not sixteen live conversations or native-speaker pronunciation tests. Planner EN/RU/KK. Kazakh shell localization is partial and some controls fall back to English.',
  source_sha256: {
    ...sourceHashes,
    'scripts/build_presentation_ru.mjs': digest(await fs.readFile(path.join(root, 'scripts/build_presentation_ru.mjs'))),
    'artifacts/presentation-ru.pptx': digest(await fs.readFile(outputPptx)),
    'artifacts/presentation-ru.pdf': digest(await fs.readFile(path.join(root, 'artifacts/presentation-ru.pdf'))),
  },
  validation, requires_visual_review: true,
}, null, 2) + '\n');
console.log(JSON.stringify({ slides: 12, build, pptx: outputPptx, pdf: path.join(root, 'artifacts/presentation-ru.pdf') }));
// All exports and verification writes have completed. Stop the native renderer
// explicitly rather than leaving its worker cleanup to the implicit event loop.
process.exit(0);
