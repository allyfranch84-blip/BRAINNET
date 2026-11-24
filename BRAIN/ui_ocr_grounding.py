"""Foveal OCR grounding for a selected foreground window.
Read-only pixel evidence, no model inference, no image file or persistent text.
"""
from functools import lru_cache
import hashlib


@lru_cache(maxsize=1)
def _eye():
    from vision_eye import RealVisionEngine
    return RealVisionEngine()


def _capture(rect):
    import mss
    from PIL import Image
    from perceptual_present import read_spatial
    physical=read_spatial()
    if physical['monitor_status']!='OBSERVED':
        raise ValueError('physical displays unavailable')
    expected={tuple(m['rect']) for m in physical['monitors']}
    with mss.mss() as sct:
        actual={(m['left'],m['top'],m['left']+m['width'],m['top']+m['height']) for m in sct.monitors[1:]}
        if actual!=expected:
            raise ValueError('physical/MSS registration mismatch')
        left,top,right,bottom=rect
        if right<=left or bottom<=top or (right-left)*(bottom-top)>8_000_000:
            raise ValueError('capture size invalid')
        if not any(l<=left and t<=top and right<=r and bottom<=b for l,t,r,b in expected):
            raise ValueError('ROI spans displays or lies outside display')
        image=sct.grab({'left':left,'top':top,'width':right-left,'height':bottom-top})
        return Image.frombytes('RGB',image.size,image.bgra,'raw','BGRX')


def _window_roi(window):
    import ctypes
    from ctypes import wintypes
    from perceptual_present import read_spatial
    from ui_motor_context import same_window
    if not same_window(window,foreground=True):
        raise ValueError('window not foreground')
    bounds=wintypes.RECT()
    dwm=ctypes.WinDLL('dwmapi')
    dwm.DwmGetWindowAttribute.argtypes=[wintypes.HWND,wintypes.DWORD,ctypes.c_void_p,wintypes.DWORD]
    dwm.DwmGetWindowAttribute.restype=ctypes.c_long
    if dwm.DwmGetWindowAttribute(window['hwnd'],9,ctypes.byref(bounds),ctypes.sizeof(bounds))!=0:
        raise ValueError('physical window bounds unavailable')
    rect=(bounds.left,bounds.top,bounds.right,bounds.bottom)
    monitors=read_spatial()
    if monitors['monitor_status']!='OBSERVED':
        raise ValueError('display topology unavailable')
    rois=[]
    for m in monitors['monitors']:
        l,t,r,b=m['rect']
        x0,y0,x1,y1=max(l,rect[0]),max(t,rect[1]),min(r,rect[2]),min(b,rect[3])
        if x1>x0 and y1>y0:
            rois.append((x0,y0,x1,y1))
    if len(rois)!=1:
        raise ValueError('window spans displays; unique OCR region unavailable')
    return rois[0]


def _owner(point, window):
    import ctypes
    from ctypes import wintypes
    u=ctypes.WinDLL('user32')
    u.WindowFromPhysicalPoint.argtypes=[wintypes.POINT]
    u.WindowFromPhysicalPoint.restype=wintypes.HWND
    u.GetAncestor.argtypes=[wintypes.HWND,wintypes.UINT]
    u.GetAncestor.restype=wintypes.HWND
    hwnd=u.WindowFromPhysicalPoint(wintypes.POINT(*point))
    return bool(hwnd and u.GetAncestor(hwnd,2)==window['hwnd'])


def find_text(window,name):
    from ui_motor_context import normalize,same_window,center
    from execution_authority import require_action_allowed
    require_action_allowed('UI_TARGET')
    try:
        rect=_window_roi(window)
        image=_capture(rect)
        rows=_eye().extrair_texto_e_coordenadas(image)
        require_action_allowed('UI_TARGET')
        if not same_window(window,foreground=True) or _window_roi(window)!=rect:
            return {'status':'OCR_CONTEXT_CHANGED'}
        key=normalize(name)
        matches=[r for r in rows if normalize(r['texto'])==key and r['confianca']>=.85]
        if len(matches)!=1:
            return {'status':'OCR_TARGET_AMBIGUOUS' if matches else 'OCR_TARGET_NOT_FOUND',
                    'similar':[r['texto'] for r in rows if key in normalize(r['texto']) and len(r['texto'])<=80][:8]}
        row=matches[0]
        x,y,w,h=row['x'],row['y'],row['w'],row['h']
        box=(rect[0]+x,rect[1]+y,rect[0]+x+w,rect[1]+y+h)
        digest=hashlib.sha256(image.crop((x,y,x+w,y+h)).tobytes()).hexdigest()
        descriptor={'name':row['texto'],'type':'OCRText','rect':box,'digest':digest,'source':'OCR'}
        if not revalidate(center(box),window,descriptor):
            return {'status':'OCR_TARGET_STALE'}
        return {'status':'RESOLVED','control':descriptor}
    except PermissionError:
        raise
    except Exception as exc:
        return {'status':'OCR_UNAVAILABLE','error':type(exc).__name__}


def revalidate(point,window,descriptor):
    from ui_motor_context import same_window,center
    try:
        if point!=center(descriptor['rect']) or not same_window(window,foreground=True) or not _owner(point,window):
            return False
        image=_capture(descriptor['rect'])
        return hashlib.sha256(image.tobytes()).hexdigest()==descriptor['digest']
    except Exception:
        return False
