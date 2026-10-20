#!/usr/bin/env python3
"""Export the current Russian acceptance evidence with ReportLab.

Run with the Codex bundled Python runtime. Inputs are documentation and saved
observations; this exporter performs no API, browser or provider requests.
"""
from pathlib import Path
from html import escape
import hashlib
import json
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle
from pypdf import PdfReader

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts/scenarios-and-limits-ru.pdf'
SOURCE=ROOT/'artifacts/brief-scenarios-ru.json'
data=json.loads(SOURCE.read_text())
cases={c['id']:c for c in data['scenarios']}
REPORT_DATE=datetime.fromisoformat(data['generated_at']).astimezone(ZoneInfo('Asia/Almaty')).strftime('%d.%m.%Y')
COUNT_LABEL=f"{data['dataset_count']:,}".replace(',', '\u00a0')
assert data['passed']==data['total']==35
assert sum(len(c['checks']) for c in cases.values())==35
assert all(all(c['checks'].values()) for c in cases.values())
assert (ROOT/'docs/test-scenarios-ru.md').exists()
FONT=Path('/usr/share/fonts/noto')
pdfmetrics.registerFont(TTFont('QalaRU',str(FONT/'NotoSans-Regular.ttf')))
pdfmetrics.registerFont(TTFont('QalaRUBold',str(FONT/'NotoSans-Bold.ttf')))
pdfmetrics.registerFontFamily('QalaRU',normal='QalaRU',bold='QalaRUBold',italic='QalaRU',boldItalic='QalaRUBold')
INK=colors.HexColor('#232834');SLATE=colors.HexColor('#556176');BLUE=colors.HexColor('#315dff');RULE=colors.HexColor('#dce3ed');PALE=colors.HexColor('#f4f7ff')
S={
 'title':ParagraphStyle('title',fontName='QalaRUBold',fontSize=23,leading=28,textColor=INK,spaceAfter=12),
 'h':ParagraphStyle('h',fontName='QalaRUBold',fontSize=15,leading=20,textColor=INK,spaceBefore=15,spaceAfter=10),
 'body':ParagraphStyle('body',fontName='QalaRU',fontSize=10.4,leading=15,textColor=INK,spaceAfter=8),
 'small':ParagraphStyle('small',fontName='QalaRU',fontSize=9,leading=13,textColor=SLATE,spaceAfter=7),
 'cell':ParagraphStyle('cell',fontName='QalaRU',fontSize=9.4,leading=13.5,textColor=INK,spaceAfter=0),
 'head':ParagraphStyle('head',fontName='QalaRUBold',fontSize=9.4,leading=13.5,textColor=INK),
}
story=[]
def clean(s):return s.replace('—','-').replace('–','-').replace('‑','-').replace('−','-')
def p(s,style='body',raw=False):
 return Paragraph(clean(s) if raw else escape(clean(s)),S[style])
def add(s,style='body'):story.append(p(s,style))
def label(name,text):story.append(p('<b>'+escape(name)+'</b> '+escape(clean(text)),raw=True))
def source(caseid):
 urls=[x['source']['url'] for x in cases[caseid]['result']['recommendations']]
 text=' · '.join('<a href="'+escape(u,quote=True)+'" color="#315dff">'+escape(u.replace('https://www.',''))+'</a>' for u in urls)
 story.append(p('<b>Источник:</b> '+text,'small',raw=True))
def heading(code,title):
 story.append(p('<font color="#315dff">'+code+'</font>  '+escape(title),'h',raw=True))
def page(title):story.append(PageBreak());add(title,'title')
def names(caseid):return ', '.join('«'+place['name']+'» ('+place['category']+')' for place in cases[caseid]['result']['recommendations']) or 'Остановок нет'
def hours(caseid):return '; '.join('«'+place['name']+'»: '+(place.get('hours') or 'не указаны') for place in cases[caseid]['result']['recommendations'])

add('Сценарии проверки\nи ограничения','title')
add('Qala / Build with AI / Русская версия','small')
add(f"Пять сценариев задания проверены реальным FastAPI/LangGraph по текущему каталогу из {COUNT_LABEL} POI. Выполнено 35 проверок из 35. Это проверка ограничений и происхождения данных, а не оценка жюри или субъективной полезности.")
label('Условия запуска.','Русский язык; память и сохранённые предпочтения выключены. Облачные ключи пустые, погода и афиша отключены, индекс локальный. База предпочтений временная; координаты и время заданы для теста.')
label('Фиксированное время.','20.10.2026, 14:00, Asia/Almaty (UTC+05:00); ночной случай - 23:00. Все минуты на страницах 1-3 - оценка планировщика до уличной маршрутизации Valhalla.')

heading('C1','Прогулка у MEGA Silk Way')
label('Вход.','«Я возле Mega Silk Way. Хочу прогулку на 45 минут». Точка 51.0897, 71.4073; бюджет 45 минут.')
label('Ожидается.','Одна-три исходные точки рядом, объяснение выбора, занятие и суммарное время в пределах бюджета. Лишняя остановка не нужна ради количества.')
r=cases['C1-mega-walk']['result'];a=r['route']
label('Зафиксировано.',f"{names('C1-mega-walk')}. {a['total_minutes']} минут: {a['walk_minutes']} пешком + {a['visit_minutes']} на месте + {a['buffer_minutes']} запаса. {r['recommendations'][0]['action']}")
label('Ограничения.','Если расписания нет, ответ не подтверждает открытый вход или работу оборудования. Погода и состояние дорожек в этом автономном прогоне не проверены.')
source('C1-mega-walk')

heading('C2','Тихое кафе с кофе и розеткой')
label('Вход.','«Хочу тихое место с кофе и розеткой недалеко от меня». Та же точка у MEGA; бюджет 60 минут.')
label('Ожидается.','Кафе, доступное по времени; розетки и тишина подтверждаются источником либо остаются неизвестными.')
r=cases['C2-quiet-coffee']['result']
label('Зафиксировано.',f"{names('C2-quiet-coffee')}, {r['route']['total_minutes']} минут. Розетки и тихие места не подтверждены. Наличие удобств предлагается уточнить при входе.")
label('Ограничения.','У выбранного места нет power_supply. Опубликованные часы не доказывают, что дверь открыта сейчас. Отсутствие отзывов не подтверждает тишину.')
source('C2-quiet-coffee')

page('Семья и время до вылета')
heading('C3','Прогулка с ребёнком: площадка или музей')
label('Вход.','«Еду с ребёнком. Где рядом детская площадка или музей с интерактивами?» Точка у Байтерека 51.1283, 71.4305; 90 минут; группа из трёх человек.')
label('Ожидается.','Семейно релевантная категория, объяснение, занятие и реалистичные переходы. Нельзя обещать интерактивы, возрастные программы, скидки или оборудование без сведений.')
r=cases['C3-family']['result'];a=r['route']
label('Зафиксировано.',f"{names('C3-family')}. {a['total_minutes']} минут: {a['walk_minutes']} пешком + {a['visit_minutes']} посещение + {a['buffer_minutes']} запаса. Группа: {r['context']['group_size']} человека. {r['recommendations'][0]['action']}")
label('Ограничения.',f"Категория не доказывает интерактивы и детскую программу. Часы и вместимость нужно уточнить. {a['walk_minutes']} минут ходьбы могут быть неудобны с маленьким ребёнком: задайте предел, например «не более 10 минут», или смените старт.")
source('C3-family')

heading('C4','Турист: два часа до вылета')
label('Первый вход.','«Я турист, у меня 2 часа перед вылетом. Что можно посмотреть поблизости?» Тестовая точка у аэропорта 51.0222, 71.4669; 120 минут; трансфер не указан.')
label('Ожидается.','Запросить актуальное время дороги до аэропорта и учесть запас на формальности. Не скрывать возвращение и регистрацию внутри обещания экскурсии.')
label('Зафиксировано.','Прогулка не построена; возвращено уточнение airport_transfer_minutes. Сообщение объясняет резерв не менее 90 минут на аэропорт и регистрацию.')
label('Второй вход.','Старт у MEGA/EXPO, те же 120 минут и явно заданный трансфер 40 минут. Доступно max(0, 120 - 90 - 40) = 0 минут; остановок нет.')
label('Ограничения.','Резерв 90 минут - правило прототипа, а не инструкция авиакомпании. Трансфер задан пользователем, это не прогноз пробок. Требования рейса и контроль безопасности требуют отдельного уточнения.')
add('В браузерной записи отдельно проверен выбор трансфера 45 минут при 120 минутах до вылета. Он также приводит к отказу от экскурсии. Это другой вход, его нельзя смешивать с фиксированным случаем на 40 минут.','small')

page('Ночной запрос и пределы данных')
heading('C5','Необычная ночная активность')
label('Вход.','«Ищу необычную ночную активность на ближайшие 2 часа». Байтерек, 51.1283, 71.4305; 120 минут; тестовое время 20.10.2026, 23:00 (UTC+05:00).')
label('Ожидается.','Учитывать опубликованные часы и правила входа. Не придумывать сегодняшнее мероприятие, доступ на крышу или разрешение на посещение.')
r=cases['C5-late-night']['result'];a=r['route']
label('Зафиксировано.',f"{names('C5-late-night')}. Оценка {a['total_minutes']} минут: {a['walk_minutes']} пешком + {a['visit_minutes']} посещение + {a['buffer_minutes']} запаса. Часы из источника: {hours('C5-late-night')}. Действия предлагают уточнить правила входа и обратную дорогу.")
label('Ограничения.','Это подбор заведений по расписанию, а не афиша; отдельный календарь в этом прогоне отключён. Текущий вход, освещение, транспорт и безопасность пути не проверены. Возраст и правила входа нужно уточнить.')
source('C5-late-night')

add('Общие ограничения','h')
label('Маршруты и карта.','В фиксированном отчёте используются оценочные соединения точек. В приложении Valhalla прокладывает пешеходный путь и пересчитывает время; превышение бюджета блокирует старт. Входы, временные перекрытия и отсутствие ступеней требуют проверки. 3D-экструзии - схема картографических контуров, а не точные модели зданий.')
label('Доступность.','Фильтр коляски требует явного wheelchair=yes у места. Он не подтверждает доступность всех улиц, переходов и входов маршрута.')
label('Каталог и источники.','Это срез OpenStreetMap, Overture Maps и Wikidata, а не полный реестр физических мест. Розетки, тишина и оборудование часто не описаны. Фото и отзывы имеют частичное покрытие. Неизвестное значение не заменяется выдуманным фактом.')
label('Память.','Предпочтения сохраняются только по согласию, доступны для просмотра, изменения и удаления, срок хранения - 30 дней. Переписка и точные координаты в память предпочтений не записываются; в политике предусмотрено округление выбранной точки до 0,01°. Поздний ответ не должен восстанавливать удалённый профиль.')

page('Доказательства и воспроизведение')
add('Что проверено и каким способом','h')
rows=[
 ['Уровень','Наблюдение и граница доказательства'],
 ['Фиксированные сценарии',f"35/35 условий на {data['dataset_count']} POI: FastAPI/LangGraph, фиксированные часы и координаты, без облачных моделей, погоды и афиши. Не проверка открытой двери или реального путешествия."],
 ['Карта и интерфейс','Каталог карты, кластеры, выбор места и сохранение маршрута проверяются отдельно в map-catalog-verification.json. Записи действий и хеши сборок находятся в материалах демо. Эти проверки не входят в 35 сценарных условий.'],
 ['Голосовые интеграции','AlemPlus распознал тестовые аудиофайлы через реальные API. Настройка 16 языков ElevenLabs прочитана обратно у поставщика; выдача частной сессии проверена. Это не 16 проведённых разговоров и не оценка произношения.'],
 ['Что не доказано','Вход микрофона в воспроизводимых записях синтетический. Физический микрофон человека и реальный телефонный звонок SIP/Twilio не проверены. Успех API и тестового сценария не подтверждает текущий вход в заведение.'],
]
t=Table([[p(v,'head' if i==0 else 'cell') for v in row] for i,row in enumerate(rows)],colWidths=[113,378])
t.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('BACKGROUND',(0,0),(-1,0),PALE),('LINEBELOW',(0,0),(-1,-1),.6,RULE),('LEFTPADDING',(0,0),(-1,-1),9),('RIGHTPADDING',(0,0),(-1,-1),9),('TOPPADDING',(0,0),(-1,-1),9),('BOTTOMPADDING',(0,0),(-1,-1),9)]))
story.append(t)
add('Как повторить','h')
add('Запуск: .venv/bin/python scripts/verify_brief_scenarios_ru.py. Скрипт обновляет JSON и Markdown из реальных ответов текущего каталога; имена мест не зашиты в ожидания. Облачные провайдеры, погода и афиша принудительно отключены после dotenv, память временная. Проверять ограничения, а не буквальное совпадение фраз.')
add('Не объявлять процент «точности» или удовлетворённости без размеченной выборки и независимой методики. 35/35 означает выполнение перечисленных проверок ограничений.','small')
add('Файлы доказательств в комплекте','h')
add('docs/test-scenarios-ru.md - подробные сценарии и дополнительные условия приёмки.\nartifacts/brief-scenarios-ru.json - полные входы, ответы, исходные ID и 35 проверок.\nartifacts/map-catalog-verification.json - карта и каталог.\nartifacts/voice-language-configuration-verification.json - фактические настройки голоса.\nartifacts/api-readiness-2026-10-20.json - отдельные живые API-проверки.\nartifacts/planner-hook-race-verification.json - гонки состояния и памяти.','small')
add('SHA-256 среза каталога: '+data['dataset_sha256'],'small')
add('Источники: OpenStreetMap, Overture Maps, Wikidata. Ссылки на выбранные объекты приведены рядом со сценариями. Отчёт сформирован '+REPORT_DATE+'.','small')

W,H=A4
def frame(canvas,doc):
 canvas.setStrokeColor(RULE);canvas.setLineWidth(.6);canvas.line(18*mm,H-15*mm,W-18*mm,H-15*mm)
 canvas.setFillColor(SLATE);canvas.setFont('QalaRU',8)
 canvas.drawString(18*mm,H-11*mm,'Qala / Проверка прототипа')
 canvas.drawString(18*mm,12*mm,REPORT_DATE+' · Сценарии и ограничения')
 canvas.drawRightString(W-18*mm,12*mm,f'{doc.page} / 4')

doc=SimpleDocTemplate(str(OUT),pagesize=A4,leftMargin=18*mm,rightMargin=18*mm,topMargin=22*mm,bottomMargin=21*mm,title='Qala - Сценарии проверки и ограничения',author='Qala project')
doc.build(story,onFirstPage=frame,onLaterPages=frame)
reader=PdfReader(OUT)
assert len(reader.pages)==4,len(reader.pages)
text='\n'.join(page.extract_text() for page in reader.pages)
for value in ['C1','C2','C3','C4','C5','35','синтетический','SIP/Twilio',str(data['dataset_count'])]+[place['name'] for case in cases.values() for place in case['result']['recommendations']]:assert value in text,value
assert '\ufffd' not in text
report={'pages':len(reader.pages),'dataset_count':data['dataset_count'],'dataset_sha256':data['dataset_sha256'],'source_checks':data['passed'],'source_total':data['total'],'exporter':'ReportLab with embedded Noto Sans Cyrillic; pypdf text verification; Poppler visual rendering','inputs':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [SOURCE,ROOT/'docs/test-scenarios-ru.md',ROOT/'scripts/verify_brief_scenarios_ru.py',Path(__file__)]},'separate_evidence':['artifacts/map-catalog-verification.json','artifacts/voice-language-configuration-verification.json','artifacts/api-readiness-2026-10-20.json'],'scope':'35 fixed-input functional scenario checks; map, current recordings, provider calls and multilingual voice configuration are separate evidence.','output':str(OUT.relative_to(ROOT)),'sha256':hashlib.sha256(OUT.read_bytes()).hexdigest()}
(ROOT/'artifacts/scenarios-and-limits-ru-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(OUT)
