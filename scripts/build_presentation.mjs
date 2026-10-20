/** Reproducible editable Qala pitch. Requires the Codex bundled artifact runtime.
 * QALA_RUNTIME_DIR can point to another configured codex-primary-runtime root.
 * Run with the bundled Node executable after app screenshots exist.
 */
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import { pathToFileURL } from 'node:url';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';

const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
const runtime = process.env.QALA_RUNTIME_DIR || path.join(os.homedir(), '.cache/codex-runtimes/codex-primary-runtime');
const skill = process.env.QALA_PRESENTATION_SKILL || path.join(os.homedir(), '.codex/plugins/cache/openai-primary-runtime/presentations/26.1015.12040/skills/presentations');
const python = path.join(runtime, 'dependencies/python/bin/python3');
const modulePath = path.join(runtime, 'dependencies/node/node_modules/@oai/artifact-tool/dist/artifact_tool.mjs');
process.env.RUNTIME_NODE_MODULES ||= path.join(runtime, 'dependencies/node/node_modules');
const { Presentation, PresentationFile } = await import(pathToFileURL(modulePath).href);
const { finalizePresentation } = await import(pathToFileURL(path.join(skill, 'container_tools/artifact_tool_utils.mjs')).href);
const build = path.join(root, '.presentation-build', String(Date.now()));
const output = path.join(root, 'artifacts');
const screenshot = path.resolve(root, process.env.QALA_SCREENSHOT || 'artifacts/screenshots/desktop.png');
await fs.access(screenshot);
await fs.mkdir(build, { recursive: true });
await fs.mkdir(output, { recursive: true });
try { await fs.symlink(path.join(runtime, 'dependencies/node/node_modules'), path.join(build, 'node_modules'), 'dir'); } catch (e) { if (e.code !== 'EEXIST') throw e; }

const C = { ivory:'#F6F4E9', pine:'#183F35', chartreuse:'#D5E875', ink:'#172B25', muted:'#5B6C60', rule:'#CDD4C5', white:'#FFFFFF' };
const deck = Presentation.create({ slideSize: { width:1280, height:720 } });
const notes = (await fs.readFile(path.join(root, 'docs/pitch-script.md'), 'utf8')).split(/## Slide \d+: /).slice(1,10);
const text = (s, value, x, y, w, h, size=28, color=C.ink, bold=false) => {
  const shape = s.shapes.add({ geometry:'textbox', name:value.slice(0,55), position:{left:x,top:y,width:w,height:h}, fill:'none', line:{fill:'none',width:0} });
  shape.text=value;
  shape.text.style={typeface:'Inter',fontSize:size,color,bold,verticalAlignment:'top',wrap:'square',autoFit:'none',insets:0};
  return shape;
};
const slide = (title, {dark=false, background}={}) => {
  const s=deck.slides.add();s.background.fill=background || (dark?C.pine:C.ivory);
  if(title) text(s,title,64,54,1152,95,50,dark?C.ivory:C.pine,true);
  text(s,String(deck.slides.items.length).padStart(2,'0'),1164,660,52,28,18,dark?C.chartreuse:C.muted);
  return s;
};
const image = async(s,file,x,y,w,h,fit='cover',alt='',crop) => {const b=await fs.readFile(path.isAbsolute(file)?file:path.join(root,file));s.images.add({blob:b.buffer.slice(b.byteOffset,b.byteOffset+b.byteLength),contentType:'image/png',alt,fit,...(crop?{crop}:{}),position:{left:x,top:y,width:w,height:h}});};
const sourceNotes=(s,index,sources='')=>{s.speakerNotes.text=(notes[index]||'')+'\n\nSources and disclosures:\n'+sources;};

// One editorial composition with an original illustrative city montage.
{
  const s=slide('');
  await image(s,'public/images/astana-editorial.png',640,0,640,720,'cover','AI-generated artistic montage inspired by Astana. Not a literal location or route.');
  text(s,'Qala',64,106,540,155,128,C.pine,true);
  text(s,'A useful next hour\nin Astana',68,299,515,170,51,C.pine);
  text(s,'A city companion grounded in local places',68,520,490,76,27,C.muted);
  text(s,'Build with AI · Astana',68,651,480,30,21,C.muted);
  sourceNotes(s,0,'Original generated illustration supplied by the project. Artistic city montage, not evidence of real spatial co-location. Product requirements: supplied hackathon brief.');
}
{
  const s=slide('A decision with real constraints',{dark:true});
  text(s,'“I’m near MEGA.\nI have 45 minutes.”',64,188,720,210,63,C.ivory,true);
  text(s,'A useful answer fits the\ntime a person actually has.',68,480,640,108,32,C.chartreuse);
  text(s,'LOCATION',882,203,290,36,22,C.chartreuse,true);
  text(s,'Nearby, not across town',882,245,295,76,27,C.ivory);
  text(s,'CONTEXT',882,347,290,36,22,C.chartreuse,true);
  text(s,'Family, coffee, access,\na flight or a late evening',882,389,305,100,27,C.ivory);
  text(s,'EVIDENCE',882,527,290,36,22,C.chartreuse,true);
  text(s,'A source for each place',882,569,305,68,27,C.ivory);
  sourceNotes(s,1,'The 45-minute request is an illustrative user input from the brief, not a performance metric. Scenario coverage: docs/test-scenarios.md.');
}
{
  const s=slide('The working prototype');
  await image(s,screenshot,64,158,1152,462,'cover','Working Qala web app, cropped to request controls, city map and grounded recommendations.',{left:.17,top:.35,right:.04,bottom:.02});
  text(s,'Simulated location. Collected POIs. No cloud keys required for the core planner.',64,642,1090,45,24,C.muted);
  sourceNotes(s,2,'Screenshot of the local Qala implementation. Demonstrate walk preset, one evidence detail and coffee preset. Offline grounded mode is a deterministic planner over collected data, not a live LLM response.');
}
{
  const s=slide('The RAG flow');
  const stages=[['01','Context','Location, time,\nlanguage and needs'],['02','Retrieval','BM25, local vectors,\ninterests and distance'],['03','Constraints','Hours, access,\ntravel and visit budget'],['04','Response','Corpus places,\nshort reasons and actions'],['05','Memory','Preferences only,\nwith opt-in and expiry']];
  for(let i=0;i<stages.length;i++) {const [n,h,b]=stages[i],x=64+i*232;text(s,n,x,201,212,87,66,C.muted);text(s,h,x,313,215,62,31,C.pine,true);text(s,b,x,398,213,160,25,C.ink);}
  text(s,'LangGraph coordinates each stage. The model cannot create place facts.',64,603,1100,70,31,C.pine,true);
  sourceNotes(s,3,'Implementation: backend/retrieval.py and graph implementation. Hybrid score combines normalized BM25, nonnegative cosine, tag overlap and proximity. Bundled vectors are 512D lexical feature hashing with multilingual aliases, not pretrained neural embeddings. Walking uses haversine × 1.3 and a pace estimate. LangChain document/vector-store interfaces; LangGraph state graph.');
}
{
  const s=slide('Evidence and uncertainty');
  text(s,'National Museum',64,180,600,70,45,C.pine,true);
  text(s,'Monday\nclosed',64,278,570,183,72,C.pine,true);
  text(s,'The venue’s official schedule\nchanges the recommendation.',68,523,550,100,29,C.muted);
  text(s,'POI EVIDENCE',734,190,440,40,22,C.muted,true);
  text(s,'Source, coordinates, category\nand recorded opening hours',734,246,465,105,30,C.ink);
  text(s,'ESTIMATES AND IDEAS',734,400,440,40,22,C.muted,true);
  text(s,'Walking time is an estimate.\nAn activity is a suggestion.\nUnknown amenities stay unknown.',734,456,473,160,29,C.ink);
  sourceNotes(s,4,'National Museum official page, accessed 19 October 2026: https://www.nmrk.kz/en/ states 10:00–18:00 Tuesday–Sunday and Monday off. The site also reports exceptions. Regular hours are not live ticket or entry availability. This slide deliberately does not assert current real-time opening.');
}
{
  const s=slide('Existing products');
  text(s,'The focus is local evidence and explicit limits.',64,133,1120,46,29,C.muted);
  const values=[['Product','Established capability','Qala’s product lesson'],['Google Maps','Conversational local discovery','Useful actions follow the answer'],['Wanderlog','AI itineraries and route optimization','Keep map and plan together'],['Mindtrip','Remembered travel preferences','Make memory deliberate'],['VoiceMap / izi.TRAVEL','Location-aware audio experiences','Voice needs trustworthy content']];
  const t=s.tables.add({rows:5,columns:3,left:64,top:214,width:1152,height:362,columnWidths:[255,445,452],values});
  t.styleOptions={headerRow:false,bandedRows:false};
  t.borders.assign({style:'solid',fill:C.rule,width:1});
  for(let r=0;r<5;r++){t.rows[r].height=r?75:62;for(let c=0;c<3;c++){const cell=t.getCell(r,c);cell.fill=r===0?C.pine:C.ivory;cell.text.style={typeface:'Inter',fontSize:r===0?23:24,color:r===0?C.ivory:C.ink,bold:r===0,wrap:'square',verticalAlignment:'middle',insets:12};}}
  text(s,'Public product claims, reviewed October 2026. No comparative performance benchmark.',64,618,1100,52,23,C.muted);
  sourceNotes(s,5,'Primary sources: https://blog.google/products-and-platforms/products/maps/ask-maps-immersive-navigation/ (12 March 2026); https://wanderlog.com/trip-planner-ai ; https://mindtrip.ai/ ; https://voicemap.me/walking-tour-app ; https://www.izi.travel/en/app . Research: docs/research/product-research.md. Absence from official material does not establish absence of a competitor feature.');
}
{
  const s=slide('Privacy and optional voice',{dark:true});
  await image(s,'public/images/astana-night.png',792,168,424,449,'cover','AI-generated illustration of Astana at night, not evidence of an actual event or route.');
  text(s,'Location stays under\nyour control',64,182,655,150,48,C.ivory,true);
  text(s,'A chosen landmark by default.\nPrecise coordinates stay out of memory.',64,364,655,100,28,C.ivory);
  text(s,'Opt-in preferences. Thirty-day expiry.\nDeletion by session.',64,485,655,90,28,C.chartreuse);
  text(s,'ElevenLabs and phone integrations require provider setup and credentials.',64,626,1090,60,25,C.ivory);
  sourceNotes(s,6,'Memory implementation: SQLite preferences, hashed bearer session IDs, coordinates rounded to 0.01°, 30-day TTL, GET/DELETE memory endpoints. Coarse location and session hashes are pseudonymous, not anonymous. Voice synthesis, signed browser agent sessions and Twilio inbound integration are implemented configuration-dependent paths. No successful real phone call is claimed. Illustration generated by project. Design reference, not Kazakhstan legal certification: https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/childrens-information/childrens-code-guidance-and-resources/age-appropriate-design-a-code-of-practice-for-online-services/10-geolocation/');
}
{
  const s=slide('Pilot and business model');
  text(s,'Free for visitors',64,190,550,70,43,C.pine,true);
  text(s,'Distribution through hotels, museums,\nuniversities and visitor information.',64,281,555,110,30,C.ink);
  text(s,'Partner tooling',734,190,480,70,43,C.pine,true);
  text(s,'Test paid tools for verified details\nand locally curated walking collections.',734,281,480,145,30,C.ink);
  text(s,'First measurements',64,482,550,55,30,C.pine,true);
  text(s,'Useful choices. Constraint violations.\nStale records. Cost per completed plan.',64,552,1100,90,29,C.muted);
  text(s,'Hypotheses. No claimed revenue, pricing validation or signed partners.',734,482,480,130,26,C.muted);
  sourceNotes(s,7,'Business model and partner channels are proposed hypotheses for a pilot, not established demand or revenue. No market size or conversion statistic is claimed. Commercial ranking policy: disclosed referrals only, no silent override of relevance. See docs/product.md.');
}
{
  const s=slide('The next pilot',{background:C.chartreuse});
  text(s,'A few suggestions\nthat fit the time\nyou have',64,178,750,286,63,C.pine,true);
  text(s,'TODAY',896,198,300,37,22,C.pine,true);
  text(s,'Local app and corpus\nAutomated collection\nTests and artifacts',896,252,310,155,27,C.pine);
  text(s,'NEXT',896,468,300,37,22,C.pine,true);
  text(s,'Verified partner updates\nPedestrian routing\nVisitor usefulness study',896,523,310,135,27,C.pine);
  text(s,'Sources and limitations travel with every recommendation.',68,552,708,100,31,C.pine);
  sourceNotes(s,8,'Current implementation and artifacts are local prototype deliverables. Planned partner updates, street routing and user study are not implemented production capabilities. YouTube publication needs an authorized account and actual upload. Source brief: supplied attachment.');
}

for(let i=0;i<deck.slides.items.length;i++){
  const s=deck.slides.items[i];
  await fs.writeFile(path.join(build,`slide-${String(i+1).padStart(2,'0')}.png`),new Uint8Array(await (await deck.export({slide:s,format:'png',scale:1})).arrayBuffer()));
  await fs.writeFile(path.join(build,`slide-${String(i+1).padStart(2,'0')}.layout.json`),await (await s.export({format:'layout'})).text());
}
const candidate=path.join(build,'candidate.pptx');
await (await PresentationFile.exportPptx(deck)).save(candidate);
const finalPath=path.join(build,'output/presentation.pptx');
await fs.mkdir(path.dirname(finalPath),{recursive:true});
const result=await finalizePresentation({workspaceDir:root,candidatePath:candidate,finalPath,pythonExecutable:python,integrityValidatorPath:path.join(skill,'container_tools/inspect_presentation_package_integrity.py'),layoutValidatorPath:path.join(skill,'container_tools/inspect_presentation_layout_geometry.py'),layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-bullet-geometry','--validate-heading-fit','--require-native-table-slide','6'],explicitTotalSlideCount:9,requiredNativeTableOwnerSlides:[6],requiredNativeChartOwnerSlides:[],fontPolicy:{basis:'design',families:['Inter']},verifyArtifactToolImport:true,receiptPath:path.join(build,'validation.json')});
console.log(JSON.stringify(result));
// Copy only a fully validated candidate to the stable submission filename.
await fs.copyFile(finalPath,path.join(output,'presentation.pptx'));
// The configured Artifact Tool bundle's direct PDF exporter has a missing
// #standard-fonts/Helvetica resource. Convert the validated editable PPTX with
// the bundled LibreOffice exporter, then render/inspect the resulting PDF.
const run = promisify(execFile);
const soffice = process.env.QALA_SOFFICE || path.join(runtime,'dependencies/bin/override/soffice');
await fs.rm(path.join(output,'presentation.pdf'),{force:true});
await run(soffice,['--headless',`-env:UserInstallation=${pathToFileURL(path.join(build,'lo-profile')).href}`,'--convert-to','pdf:impress_pdf_Export','--outdir',output,finalPath],{timeout:90000});
await fs.writeFile(path.join(build,'montage.webp'),new Uint8Array(await (await deck.export({format:'webp',montage:true})).arrayBuffer()));
console.log('Created editable PPTX, PDF and private slide previews.');
