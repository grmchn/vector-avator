"""Compile authored vector parts; never extracts character pixels from a PNG.
Requires svgpathtools; qa additionally needs Pillow and an Inkscape CLI.
"""
import argparse, copy, json, math, re, subprocess
from pathlib import Path
import xml.etree.ElementTree as ET
from svgpathtools import parse_path, Line, CubicBezier, QuadraticBezier

SVG='http://www.w3.org/2000/svg'; INK='http://www.inkscape.org/namespaces/inkscape'
ET.register_namespace('',SVG); ET.register_namespace('inkscape',INK)

def require(ok, message):
    if not ok: raise ValueError(message)

def number(v):
    return type(v) in (int,float) and math.isfinite(v)

def cubic_path(d):
    require(isinstance(d,str) and d.strip(), 'Path d must be nonempty')
    path=parse_path(d); result=[]
    require(len(path)>0,'Empty geometry')
    for sub in path.continuous_subpaths():
        segments=[]
        for seg in sub:
            if isinstance(seg,Line): pts=[seg.start,seg.start+(seg.end-seg.start)/3,seg.start+2*(seg.end-seg.start)/3,seg.end]
            elif isinstance(seg,QuadraticBezier): pts=[seg.start,seg.start+2*(seg.control-seg.start)/3,seg.end+2*(seg.control-seg.end)/3,seg.end]
            elif isinstance(seg,CubicBezier): pts=[seg.start,seg.control1,seg.control2,seg.end]
            else: raise ValueError('Use M/L/C/Q/Z; convert arcs to cubic curves explicitly')
            require(all(math.isfinite(z.real) and math.isfinite(z.imag) for z in pts),'Non-finite path coordinate')
            segments.append([[z.real,z.imag] for z in pts])
        result.append({'closed':sub.isclosed(),'segments':segments})
    return result

def load_art(file):
    art=json.loads(Path(file).read_text(encoding='utf-8-sig'))
    require(art.get('schema_version')==1,'schema_version must be 1')
    require(all(type(art.get(k))==int and 0<art[k]<=8192 for k in ['width','height']),'Canvas must use positive integer dimensions <=8192')
    parts=art.get('parts',[]); require(parts,'No parts')
    ids=[p.get('id') for p in parts]
    require(all(isinstance(i,str) and re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*',i) for i in ids),'Use safe unique part IDs')
    require(len(set(ids))==len(ids),'Duplicate part IDs')
    compiled=copy.deepcopy(art); warnings=[]; segment_count=0
    for i,p in enumerate(compiled['parts']):
        require(isinstance(p.get('label'),str) and p['label'],'Every part needs label')
        require(p.get('parent') is None or p['parent'] in ids,'Missing parent: '+p['id'])
        require(type(p.get('visible'))==bool,'Every part needs visible boolean')
        require(len(p.get('pivot',[]))==2 and all(number(n) for n in p['pivot']),'Invalid pivot')
        require(isinstance(p.get('coverage'),str) and p['coverage'].strip(),'Describe hidden completion / no occlusion in coverage: '+p['id'])
        require(isinstance(p.get('shapes'),list) and p['shapes'],'Empty part '+p['id'])
        p['order']=i
        for j,s in enumerate(p['shapes']):
            require(set(s)<=set(['name','d','fill','stroke','width']),'Unsupported shape fields; raster/masks/transforms are not this schema')
            require(isinstance(s.get('name'),str) and s['name'],'Shape needs name')
            require(all(s.get(k) is None or (isinstance(s[k],str) and re.fullmatch(r'#[0-9A-Fa-f]{6}',s[k])) for k in ['fill','stroke']),'Use #RRGGBB or null colors')
            require(s.get('fill') or s.get('stroke'),'Invisible shape')
            require(number(s.get('width',0)) and s.get('width',0)>=0,'Bad stroke width')
            require(not s.get('stroke') or s.get('width',0)>0,'Stroke must have positive width')
            s['splines']=cubic_path(s.get('d'))
            if s.get('fill'):
                require(len(s['splines'])==1 and s['splines'][0]['closed'],'Filled path needs one closed contour; decompose holes/multiple contours')
            n=sum(len(sub['segments']) for sub in s['splines']);segment_count+=n
            if n>80:warnings.append(f'{p["id"]}/{s["name"]}: {n} segments; inspect for unnecessary trace noise')
        ancestors=set(); current=p
        while current.get('parent'):
            require(current['id'] not in ancestors,'Parent cycle')
            ancestors.add(current['id']);current=compiled['parts'][ids.index(current['parent'])]
    qa=art.get('qa',[])
    require(any(q.get('kind')=='reveal' for q in qa),'Add a reveal QA case')
    require(any(q.get('kind')=='move' for q in qa),'Add a motion-envelope QA case')
    names=[]
    for q in qa:
        require(q.get('kind') in ['reveal','move','expression'],'Bad QA kind')
        require(isinstance(q.get('name'),str) and re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*',q['name']),'QA name must be filename-safe')
        require(q['name'] not in ['neutral','parts','parts_contact','review_checks'],'Reserved QA filename')
        names.append(q['name']); require(q.get('check'),'QA needs a visual check description')
        for k in ['hide','show']:require(all(i in ids for i in q.get(k,[])),'Unknown part in QA')
        for key,t in q.get('transforms',{}).items():
            require(key in ids and set(t)<=set(['dx','dy','deg']) and all(number(v) for v in t.values()),'Invalid QA transform')
        if q['kind']=='reveal':require(q.get('hide'),'Reveal must hide occluders')
        if q['kind']=='move':require(any(any(v!=0 for v in t.values()) for t in q.get('transforms',{}).values()),'Move QA must actually move a part')
    require(len(names)==len(set(names)),'Duplicate QA names')
    return art,compiled,{'parts':len(parts),'paths':sum(len(p['shapes']) for p in parts),'cubic_segments':segment_count,'warnings':warnings,'structural_only':True}

def mul(a,b):
    x,y,z,w,u,v=a;A,B,C,D,E,F=b
    return (x*A+z*B,y*A+w*B,x*C+z*D,y*C+w*D,x*E+z*F+u,y*E+w*F+v)

def svg(art, case=None, only=None):
    case=case or {}; hidden=set(case.get('hide',[])); shown=set(case.get('show',[]))
    by_id={p['id']:p for p in art['parts']}; memo={}
    def transform(p):
        if p['id'] in memo:return memo[p['id']]
        t=case.get('transforms',{}).get(p['id'],{});r=math.radians(t.get('deg',0));c=math.cos(r);s=math.sin(r);x,y=p['pivot']
        m=(c,s,-s,c,x-c*x+s*y+t.get('dx',0),y-s*x-c*y+t.get('dy',0))
        if p.get('parent'):m=mul(transform(by_id[p['parent']]),m)
        memo[p['id']]=m;return m
    root=ET.Element(f'{{{SVG}}}svg',{'width':str(art['width']),'height':str(art['height']),'viewBox':f'0 0 {art["width"]} {art["height"]}'})
    for i,p in enumerate(art['parts']):
        if only is not None and p['id']!=only:continue
        attrs={'id':p['id'],f'{{{INK}}}groupmode':'layer',f'{{{INK}}}label':f'{i:02d}_{p["id"]} / {p["label"]}'}
        visible=(p['visible'] or p['id'] in shown) and p['id'] not in hidden
        if only is None and not visible:attrs['style']='display:none'
        if case.get('transforms'):attrs['transform']='matrix('+ ' '.join(f'{n:.9g}' for n in transform(p))+')'
        g=ET.SubElement(root,f'{{{SVG}}}g',attrs)
        for j,s in enumerate(p['shapes']):
            ET.SubElement(g,f'{{{SVG}}}path',{'id':f'{p["id"]}_{j:03d}','d':s['d'],'fill':s.get('fill') or 'none','stroke':s.get('stroke') or 'none','stroke-width':str(s.get('width',0)),'stroke-linecap':'round','stroke-linejoin':'round'})
    return root

def write_svg(root,file):
    ET.ElementTree(root).write(file,encoding='utf-8',xml_declaration=True)

def build(art,compiled,report,out):
    out.mkdir(parents=True,exist_ok=True)
    for name in ['layers','variants']:(out/name).mkdir(exist_ok=True)
    write_svg(svg(art),out/'character_layers.svg');manifest=[]
    for i,p in enumerate(art['parts']):
        filename=f'{"layers" if p["visible"] else "variants"}/{i:02d}_{p["id"]}.svg'
        write_svg(svg(art,only=p['id']),out/filename)
        manifest.append({'order':i,'id':p['id'],'label':p['label'],'file':filename,'visible':p['visible'],'parent':p.get('parent'),'pivot':p['pivot'],'coverage':p['coverage']})
    for name,data in [('art.json',art),('compiled.json',compiled),('layers.json',manifest),('structure_report.json',report)]:
        (out/name).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    # This compares drawable path structures, not rendering or artistic quality.
    stacked=[]
    for row in manifest:
        if row['visible']:stacked.extend(list(ET.parse(out/row['file']).getroot())[0])
    expected=[s for g in svg(art) if g.get('style')!='display:none' for s in g]
    require([e.attrib for e in stacked]==[e.attrib for e in expected],'Numbered parts do not match combined SVG')

def render_svg(file,target,inkscape):
    result=subprocess.run([str(inkscape),str(file.resolve()),'--export-type=png','--export-area-page',f'--export-filename={target.resolve()}'],capture_output=True)
    require(result.returncode==0,'Inkscape failed: '+result.stderr.decode('utf-8',errors='replace'))
    require(target.exists(),'Inkscape did not produce '+str(target))

def qa(art,out,inkscape):
    from PIL import Image,ImageDraw
    out.mkdir(parents=True,exist_ok=True)
    cases=[{'name':'neutral','check':'Compare identity, silhouette and overlap to reference'}]+art['qa']
    for case in cases:
        path=out/(case['name']+'.svg');write_svg(svg(art,case),path);render_svg(path,path.with_suffix('.png'),inkscape)
    thumbs=out/'parts';thumbs.mkdir(exist_ok=True)
    tile=256;cols=4;sheet=Image.new('RGB',(cols*tile,math.ceil(len(art['parts'])/cols)*(tile+32)),'#e8ebee');draw=ImageDraw.Draw(sheet)
    for i,p in enumerate(art['parts']):
        path=thumbs/(p['id']+'.svg');write_svg(svg(art,only=p['id']),path);render_svg(path,path.with_suffix('.png'),inkscape)
        im=Image.open(path.with_suffix('.png')).convert('RGBA');box=im.getchannel('A').getbbox();require(box,'Empty part '+p['id'])
        im=im.crop(box);im.thumbnail((tile-20,tile-20));x=i%cols*tile;y=i//cols*(tile+32)
        sheet.paste(im,(x+(tile-im.width)//2,y+(tile-im.height)//2),im)
        draw.text((x+8,y+tile),f'{i:02d} {p["id"]}',fill='#17233a')
    sheet.save(out/'parts_contact.png')
    (out/'review_checks.json').write_text(json.dumps(cases,ensure_ascii=False,indent=2),encoding='utf-8')
    print('QA rendered. Open neutral, parts_contact, and every case; visual review still required.')

def main():
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['validate','build','qa']);parser.add_argument('--art',required=True,type=Path);parser.add_argument('--out',type=Path);parser.add_argument('--inkscape',type=Path)
    args=parser.parse_args();art,compiled,report=load_art(args.art)
    if args.command!='validate':require(args.out is not None,'--out required')
    if args.command=='build':build(art,compiled,report,args.out)
    if args.command=='qa':require(args.inkscape is not None,'--inkscape required');qa(art,args.out,args.inkscape)
    print(json.dumps(report,ensure_ascii=False))
if __name__=='__main__':main()
