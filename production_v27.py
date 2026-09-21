from __future__ import annotations
from pathlib import Path
import json, datetime, math
from PIL import Image, ImageDraw, ImageFont

APP_VERSION='V27'
STATUSES=['New','Ready','In Production','Proofed','Approved','Hold','Archived']

def now(): return datetime.datetime.now().isoformat(timespec='seconds')

def enrich_item(item, tags=None, notes=None, print_status=None):
    x=dict(item)
    x['tags']=list(tags if tags is not None else item.get('tags',[]))
    x['notes']=notes if notes is not None else item.get('notes','')
    x['print_status']=print_status if print_status is not None else item.get('print_status','New')
    return x

def save_library_v27(path, items, favorites=None):
    Path(path).write_text(json.dumps({'version':APP_VERSION,'saved_at':now(),'items':items,'favorites':sorted(favorites or [])},indent=2,ensure_ascii=False),encoding='utf-8')

def load_library_v27(path):
    d=json.loads(Path(path).read_text(encoding='utf-8'))
    items=[enrich_item(x) for x in d.get('items',[])]
    return items,set(d.get('favorites',[]))

def make_contact_sheet(items, output, thumb=(220,170), columns=4, margin=24, gap=18, background=(28,28,32)):
    valid=[]
    for x in items:
        try:
            im=Image.open(x['path']).convert('RGBA'); valid.append((x,im))
        except Exception: pass
    if not valid: raise ValueError('No readable artwork selected.')
    rows=math.ceil(len(valid)/columns); cell_w,cell_h=thumb
    label_h=72
    W=margin*2+columns*cell_w+(columns-1)*gap
    H=margin*2+rows*(cell_h+label_h)+(rows-1)*gap
    sheet=Image.new('RGB',(W,H),background); d=ImageDraw.Draw(sheet)
    for i,(x,im) in enumerate(valid):
        col=i%columns; row=i//columns
        px=margin+col*(cell_w+gap); py=margin+row*(cell_h+label_h+gap)
        bg=Image.new('RGBA',thumb,(245,245,245,255))
        im.thumbnail(thumb,Image.Resampling.LANCZOS)
        bg.alpha_composite(im,((cell_w-im.width)//2,(cell_h-im.height)//2))
        sheet.paste(bg.convert('RGB'),(px,py))
        d.rectangle((px,py,px+cell_w-1,py+cell_h-1),outline=(100,100,105),width=1)
        name=str(x.get('name') or Path(x['path']).name)
        tags=', '.join(x.get('tags',[]))
        status=x.get('print_status','New')
        line1=name[:34]
        d.text((px,py+cell_h+8),line1,fill=(240,240,240))
        d.text((px,py+cell_h+30),f'{status}  |  {tags[:28]}',fill=(175,175,180))
    sheet.save(output,quality=94)
    return output

def make_library_report_v27(items):
    tags={}
    statuses={}
    for x in items:
        for t in x.get('tags',[]): tags[t]=tags.get(t,0)+1
        s=x.get('print_status','New'); statuses[s]=statuses.get(s,0)+1
    return {'version':APP_VERSION,'generated_at':now(),'count':len(items),'tags':dict(sorted(tags.items())), 'statuses':statuses,
            'items':[{'path':x.get('path'),'name':x.get('name'),'tags':x.get('tags',[]),'notes':x.get('notes',''),'print_status':x.get('print_status','New')} for x in items]}

def make_queue_jobs(items, options=None):
    opts=dict(options or {})
    return [{'name':Path(x['path']).stem,'source':x['path'],'options':dict(opts)} for x in items]
