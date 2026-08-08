"""Callbacks for cont_mask_combiner/webserver_mask (port 8899 — kept far from
the MCP bridge's 9980 to avoid confusion/collisions).

Serves the mask-combiner webapp and bakes sent masks into named out TOPs.
Source of truth is this repo file; the in-TD textDAT is loaded from it.
Only stdlib at module import time so tests can import it outside TD.
"""

import base64
import json
import os
import re
import tempfile
import time

APP_DIR = r'C:\Users\NICKESCHEN\dev\TD-MCP\touchdesigner\maskcombiner'
SENT_DIR = r'C:\Users\NICKESCHEN\dev\TD-MCP\touchdesigner\assets\sent_masks'
MAX_BODY = 32 * 1024 * 1024


def sanitize_name(raw):
    s = re.sub(r'[^A-Za-z0-9_]', '_', str(raw).strip())
    s = s.strip('_')
    if not s:
        return ''
    if not s[0].isalpha():
        s = 'Mask_' + s
    return s[:64]


def unique_name(base, existing):
    if base not in existing:
        return base
    i = 2
    while '%s_%d' % (base, i) in existing:
        i += 1
    return '%s_%d' % (base, i)


def onHTTPRequest(webServerDAT, request, response):
    try:
        return _dispatch(webServerDAT, request, response)
    except Exception as e:
        response['statusCode'] = 500
        response['statusReason'] = 'Internal Server Error'
        response['data'] = json.dumps({'ok': False, 'error': str(e)})
        return response


def _dispatch(webServerDAT, request, response):
    uri = request['uri']
    method = request['method']
    if method == 'GET' and uri == '/':
        return _serve_file(os.path.join(APP_DIR, 'index.html'),
                           'text/html; charset=utf-8', response)
    if method == 'GET' and uri == '/maskops.mjs':
        return _serve_file(os.path.join(APP_DIR, 'maskops.mjs'),
                           'text/javascript; charset=utf-8', response)
    if method == 'GET' and uri.split('?')[0] == '/mask':
        return _serve_mask(webServerDAT, response)
    if method == 'POST' and uri == '/send':
        return _handle_send(webServerDAT, request, response)
    response['statusCode'] = 404
    response['statusReason'] = 'Not Found'
    response['data'] = json.dumps({'ok': False, 'error': 'unknown endpoint %s %s' % (method, uri)})
    return response


def _serve_file(path, ctype, response):
    with open(path, 'rb') as f:
        response['data'] = f.read()
    response['statusCode'] = 200
    response['statusReason'] = 'OK'
    response['content-type'] = ctype
    response['Cache-Control'] = 'no-store'
    return response


def _serve_mask(webServerDAT, response):
    src = webServerDAT.parent().op('in1')
    if src is None:
        response['statusCode'] = 500
        response['data'] = json.dumps({'ok': False, 'error': 'in1 missing'})
        return response
    tmp = os.path.join(tempfile.gettempdir(), 'maskcombiner_in1.png')
    src.save(tmp)
    with open(tmp, 'rb') as f:
        response['data'] = f.read()
    response['statusCode'] = 200
    response['statusReason'] = 'OK'
    response['content-type'] = 'image/png'
    response['Cache-Control'] = 'no-store'
    return response


def _handle_send(webServerDAT, request, response):
    body = request.get('data', b'')
    if isinstance(body, bytes):
        body = body.decode('utf-8')
    if len(body) > MAX_BODY:
        return _err(response, 400, 'body too large')
    payload = json.loads(body)
    name = sanitize_name(payload.get('name', ''))
    if not name:
        return _err(response, 400, 'invalid name')
    try:
        png = base64.b64decode(payload.get('png_base64', ''), validate=True)
    except Exception:
        return _err(response, 400, 'bad png_base64')
    if not png.startswith(b'\x89PNG'):
        return _err(response, 400, 'not a png')

    comp = webServerDAT.parent()
    existing = set(c.name for c in comp.children)
    name = unique_name(name, existing)

    os.makedirs(SENT_DIR, exist_ok=True)
    fp = os.path.join(SENT_DIR, '%s_%d.png' % (name, int(time.time() * 1000)))
    while os.path.exists(fp):  # never overwrite
        fp = os.path.join(SENT_DIR, '%s_%d.png' % (name, int(time.time() * 1000) + 1))
    with open(fp, 'wb') as f:
        f.write(png)

    n_sent = len([c for c in comp.children if 'sentmask' in c.tags and c.type == 'out'])
    mfi = comp.create(moviefileinTOP, 'mfi_' + name)
    mfi.par.file = fp.replace('\\', '/')
    for pname in ('filtertype', 'inputfiltertype'):
        if hasattr(mfi.par, pname):
            getattr(mfi.par, pname).val = 'nearest'
    mfi.tags.add('sentmask')
    mfi.nodeX, mfi.nodeY = 400, -300 - 200 * n_sent

    out_op = comp.create(outTOP, name)
    out_op.tags.add('sentmask')
    out_op.nodeX, out_op.nodeY = 700, -300 - 200 * n_sent
    out_op.inputConnectors[0].connect(mfi)

    src = comp.op('in1')
    if src is not None and (mfi.width != src.width or mfi.height != src.height):
        mfi.destroy()
        out_op.destroy()
        try:
            os.remove(fp)
        except OSError:
            pass
        return _err(response, 400, 'png dimensions do not match in1 (%dx%d)' % (src.width, src.height))

    response['statusCode'] = 200
    response['statusReason'] = 'OK'
    response['content-type'] = 'application/json'
    response['data'] = json.dumps({'ok': True, 'out_path': out_op.path, 'file': fp.replace('\\', '/')})
    return response


def _err(response, code, msg):
    response['statusCode'] = code
    response['statusReason'] = 'Bad Request'
    response['content-type'] = 'application/json'
    response['data'] = json.dumps({'ok': False, 'error': msg})
    return response
