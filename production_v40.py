"""V40 Final Prepress & Quality Control Lab.
Raster-oriented preflight diagnostics for T-shirt artwork. Checks measurable properties and
flags conditions that may require operator review. It is not a calibrated RIP/ICC validator.
"""
from pathlib import Path
import json, math
from PIL import Image, ImageFilter


def _px_to_mm(px, dpi):
    return float(px) / max(float(dpi), 1.0) * 25.4


def alpha_audit(im):
    a=im.convert('RGBA').getchannel('A')
    hist=a.histogram(); total=max(1, im.width*im.height)
    transparent=sum(hist[:1]); partial=sum(hist[1:255]); opaque=hist[255]
    return {'transparent_pct':round(transparent/total*100,3),'partial_alpha_pct':round(partial/total*100,3),'opaque_pct':round(opaque/total*100,3),'has_alpha':partial>0 or transparent>0}


def dpi_print_report(im, dpi=300):
    dpi=float(dpi or 300)
    return {'dpi':dpi,'pixel_width':im.width,'pixel_height':im.height,
            'print_width_mm':round(_px_to_mm(im.width,dpi),2),'print_height_mm':round(_px_to_mm(im.height,dpi),2),
            'print_width_in':round(im.width/dpi,3),'print_height_in':round(im.height/dpi,3)}


def coverage_stats(mask):
    a=mask.convert('L'); hist=a.histogram(); total=max(1,a.width*a.height)
    active=total-hist[0]
    return {'coverage_pct':round(active/total*100,3),'width':a.width,'height':a.height}


def minimum_feature_estimate(mask, dpi=300, min_stroke_mm=0.5, min_negative_mm=0.5):
    """Conservative pixel-scale warning; does not perform true vector stroke analysis."""
    px_stroke=float(min_stroke_mm)/25.4*float(dpi)
    px_gap=float(min_negative_mm)/25.4*float(dpi)
    return {'requested_min_stroke_mm':float(min_stroke_mm),'requested_min_negative_space_mm':float(min_negative_mm),
            'equivalent_stroke_px':round(px_stroke,2),'equivalent_gap_px':round(px_gap,2),
            'note':'Raster preflight cannot reliably infer true vector stroke/negative-space dimensions.'}


def transparency_audit(im):
    a=im.convert('RGBA').getchannel('A')
    bbox=a.getbbox()
    if bbox is None: return {'has_visible_artwork':False,'bbox':None,'coverage_pct':0.0}
    x0,y0,x1,y1=bbox; area=(x1-x0)*(y1-y0); total=max(1,im.width*im.height)
    return {'has_visible_artwork':True,'bbox':[x0,y0,x1,y1],'bbox_width':x1-x0,'bbox_height':y1-y0,'bbox_coverage_pct':round(area/total*100,3)}


def channel_consistency(channels):
    if not channels: return {'channel_count':0,'consistent_sizes':True,'sizes':{},'warnings':['No separated channels supplied.']}
    sizes={str(k):list(v.size) for k,v in channels.items()}
    vals=list(sizes.values()); consistent=all(v==vals[0] for v in vals)
    return {'channel_count':len(channels),'consistent_sizes':consistent,'sizes':sizes,'warnings':([] if consistent else ['Channel dimensions do not match.'])}


def underbase_readiness(mask, threshold_pct=1.0):
    rep=coverage_stats(mask); cov=rep['coverage_pct']
    warnings=[]
    if cov<=threshold_pct: warnings.append('Underbase mask is nearly empty; verify artwork alpha/mask settings.')
    if cov>98: warnings.append('Underbase covers almost the entire sheet; check background removal and threshold.')
    return {'coverage_pct':cov,'ready':not warnings,'warnings':warnings}


def halftone_readiness(im, dpi=300, lpi=45, angle=22.5):
    dpi=float(dpi); lpi=float(lpi)
    cell=dpi/max(lpi,1)
    warnings=[]
    if cell<4: warnings.append('Very small halftone cell in pixels; screening detail may be unstable.')
    if lpi<=0: warnings.append('LPI must be positive.')
    return {'dpi':dpi,'lpi':lpi,'cell_px':round(cell,2),'screen_angle_deg':float(angle),'ready':not warnings,'warnings':warnings}


def garment_proof_readiness(im, garment='Black'):
    supported=['Black','White','Navy','Red','Royal Blue','Dark Gray','Forest Green']
    warnings=[]
    if garment not in supported: warnings.append('Garment proof color is outside the built-in proof set.')
    if im.mode not in ('RGBA','RGB'): warnings.append('Unexpected image mode; convert to RGB/RGBA before proofing.')
    return {'garment':garment,'supported':garment in supported,'ready':not warnings,'warnings':warnings}


def build_qc_report(im, dpi=300, garment='Black', min_stroke_mm=0.5, min_negative_mm=0.5,
                    lpi=45, angle=22.5, channels=None, underbase_mask=None):
    alpha=alpha_audit(im); dpi_rep=dpi_print_report(im,dpi); trans=transparency_audit(im)
    feature=minimum_feature_estimate(underbase_mask if underbase_mask is not None else im.getchannel('A'),dpi,min_stroke_mm,min_negative_mm)
    ch=channel_consistency(channels or {})
    ub=underbase_readiness(underbase_mask) if underbase_mask is not None else {'coverage_pct':None,'ready':True,'warnings':['Underbase mask not supplied; review in Underbase Lab.']}
    ht=halftone_readiness(im,dpi,lpi,angle); gp=garment_proof_readiness(im,garment)
    warnings=[]
    if not trans['has_visible_artwork']: warnings.append('No visible artwork detected.')
    if dpi < 150: warnings.append('DPI is below 150; verify intended print size/resolution.')
    if alpha['partial_alpha_pct']>30: warnings.append('Large partial-alpha area; inspect transparency before film export.')
    warnings += ch['warnings']+ub['warnings']+ht['warnings']+gp['warnings']
    status='FAIL' if any('No visible' in w or 'dimensions do not' in w for w in warnings) else ('WARNING' if warnings else 'PASS')
    return {'schema':'ImageStudio.V40.PrepressQC.1','status':status,'summary':{'warning_count':len(warnings)},
            'image':{'mode':im.mode,'size':[im.width,im.height]},'alpha_audit':alpha,'dpi_print':dpi_rep,
            'transparency':trans,'feature_check':feature,'channel_consistency':ch,'underbase':ub,
            'halftone':ht,'garment_proof':gp,'warnings':warnings,
            'checklist':{'artwork_visible':trans['has_visible_artwork'],'dpi_checked':True,'alpha_checked':True,
                         'channels_checked':True,'underbase_checked':underbase_mask is not None,'halftone_checked':True,
                         'garment_proof_checked':True,'overprint_knockout':'operator review required',
                         'icc_calibration':'not performed'}}


def save_qc_report(report, path):
    p=Path(path); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8'); return p
