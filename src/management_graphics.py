"""Native-size management surfaces, rendered with the appliance pixel font."""
import time
from graphics import INK,BRASS
from loop_model import PITCH_NAMES,MODES
from library_manager import ALPHABET
DARK=(7,14,13)

def actions(c,labels):
    c.rect(0,138,960,22,DARK)
    for index,label in enumerate(labels):
        c.text(index*120+5,143,label,BRASS,1 if len(label)>9 else 2)

def lines(c,x,y,text,width=62,color=INK):
    # Exact paths stay visible; wrapping is presentation only, no truncation.
    for n,start in enumerate(range(0,len(text),width)):c.text(x,y+n*10,text[start:start+width],color)

def film_label(record):
    state=record.get('state','idle');seconds=int(record.get('seconds',0))
    if state=='recording':return 'FILM RECORDING %02d:%02d'%(seconds//60,seconds%60)
    if state=='saving':return 'SAVING MP4 / '+str(round(record.get('encoding_seconds',0)))+'S'
    if state=='ready':return 'SAVED ON PUSH'
    if state=='error':return 'FILM ERROR / '+str(record.get('error','UNKNOWN'))
    return 'FILM OFF'

def key_page(c,m,i,rgb):
    draft=i.key_draft if i and i.key_draft else (m.state.root,m.state.scale)
    c.rect(0,45,960,115,DARK)
    for index,mode in enumerate(MODES):
        x=index*120+5;c.text(x,51,mode,INK,1 if len(mode)>8 else 2)
        if mode==m.state.scale:c.rect(x,68,108,3,rgb);c.text(x,76,'ACTIVE',rgb)
        if mode==draft[1]:
            c.line(x,48,x+108,48,BRASS);c.line(x,48,x,65,BRASS);c.line(x+108,48,x+108,65,BRASS);c.text(x,86,'CHOOSE',BRASS)
    c.text(846,54,'BACK',BRASS,2)
    c.text(6,100,'ACTIVE '+PITCH_NAMES[m.state.root%12]+' '+m.state.scale.upper(),rgb,2)
    c.text(440,100,'CHOOSE '+PITCH_NAMES[draft[0]%12]+' '+draft[1].upper(),INK,2)
    for n,name in enumerate(PITCH_NAMES):
        x=12+n*48;c.text(x,122,name,BRASS if n==draft[0]%12 else INK)
        if n==draft[0]%12:c.rect(x-2,132,26,2,BRASS)
    c.text(610,121,'ENC 1 ROOT / ENC 2 MODE / APPLY',INK)
    actions(c,['','','','','','','CANCEL','APPLY'])

def manager_page(c,m,i,record):
    c.rect(0,45,960,115,DARK);view=m.view
    title='LOOP LIBRARY' if view=='library' else 'RECORDINGS'
    c.text(6,48,title,INK,2)
    if view=='recordings':
        c.text(245,48,'CURRENT',BRASS if i.record_tab=='current' else INK,2)
        c.text(370,48,'SAVED',BRASS if i.record_tab=='saved' else INK,2)
    if view=='library':
        source=m.source_status()
        label=('LOADED '+source['name']+' / ID '+source['id'][-13:-5]+(' / DELETED' if source['deleted'] else '')+(' / EDITED' if source['modified'] else '')) if source else 'CURRENT AUTOSAVE / UNNAMED'
        c.text(245,49,label,BRASS)
    if i.manager_busy:c.text(740,49,'WORKING',BRASS,2)
    if i.rename is not None:
        c.text(6,70,i.rename or 'EMPTY NAME',INK,2)
        c.text(6+min(i.rename_cursor,24)*12,86,'|',BRASS,2)
        c.text(6,100,'ENC 1 CURSOR / ENC 2 CHARACTER',BRASS,2)
        start=max(0,i.character-8);strip=ALPHABET[start:start+24]
        c.text(6,122,'CHAR '+ALPHABET[i.character]+' / '+strip,INK)
        actions(c,['INSERT','SPACE','BACKSPACE','','','','CANCEL','SAVE NAME']);return
    if i.confirm:
        row=i.confirm['row'];loading=i.confirm['action']=='load'
        c.text(6,72,('LOAD ' if loading else 'DELETE ')+row['name'][:32],INK,2)
        c.text(6,95,row['id'],BRASS)
        text='CURRENT SONG WILL BE ARCHIVED / PLAYBACK STOPS' if loading else 'SAVED SNAPSHOT ONLY / CURRENT SONG STAYS' if view=='library' else row.get('type','')+' / '+str(row['bytes'])+' BYTES INCLUDING PRIVATE RAW FILES'
        c.text(6,111,text,INK,2)
        actions(c,['','','','','','','CANCEL','LOAD' if loading else 'DELETE']);return
    if view=='recordings' and i.record_tab=='current':
        c.text(6,71,film_label(record)[:74],INK,2)
        if i.details:
            filename=record.get('filename');path=str(i.recorder.directory/filename) if i.recorder and filename else 'NO SAVED MP4 YET'
            lines(c,6,91,path,105,BRASS)
            c.text(6,121,str(record.get('warning') or record.get('error') or 'LOCAL SAVE ON PUSH / NO COMPUTER DOWNLOAD')[:110],INK)
        else:
            c.text(6,95,'SCREEN + STEREO OUTPUT / MUSIC TRANSPORT IS INDEPENDENT',BRASS,2)
            c.text(6,116,'STOP+SAVE FINISHES THIS FILM AND SAVES AN MP4 ON PUSH',INK,2)
        actions(c,['START FILM','STOP+SAVE','EXPORT WAV','LAST 30S','SAVED','DETAILS','','BACK']);return
    row=i.selected_row();index=next((n for n,r in enumerate(i.rows) if r['id']==i.selected_id),0);start=index//4*4
    if not i.rows:c.text(6,78,'NO SAVED ITEMS / REFRESH TO CHECK',BRASS,2)
    for n,r in enumerate(i.rows[start:start+4]):
        y=69+n*16
        if r['id']==i.selected_id:c.rect(3,y-2,550,14,(32,49,44))
        c.text(7,y,r['name'][:29],INK)
        date=time.strftime('%m-%d %H:%M',time.localtime(r['created']))
        text=(r.get('key','ERROR')+' '+str(round(r.get('tempo',0)))+'BPM '+str(r.get('bars',0))+'BAR') if view=='library' else r['status']+' '+(str(round(r['seconds']))+'S' if r.get('seconds') is not None else 'UNKNOWN')
        c.text(205,y,date+' '+text[:32],BRASS)
    if row:
        lines(c,568,69,row['id'],61,BRASS)
        c.text(568,91,str(row['bytes'])+' BYTES / '+row['status'],INK)
        text=str(row.get('layers',''))+' LAYERS' if view=='library' else row.get('type','')+' / RAW '+str(row.get('raw_bytes',0))+' BYTES'
        c.text(568,104,text,BRASS)
        if i.details:lines(c,568,115,str((i.manager.saved if view=='library' else i.manager.recordings)/row['name' if view=='recordings' else 'id']),61)
        else:c.text(568,120,'RIGHT WHEEL SELECT / ARROWS PAGE',INK)
    actions(c,['SAVE NEW','LOAD','RENAME','DELETE','REFRESH','DETAILS','','BACK'] if view=='library' else ['REFRESH','DETAILS','RECOVER','DELETE','','','','BACK'])
