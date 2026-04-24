"""
TouchDesigner MCP WebServer Callbacks
=====================================
Paste this into the callback DAT of a WebServer DAT.
The WebServer DAT should be set to listen on port 9980.

This handles incoming HTTP requests from the MCP server:
  POST /execute  — Execute Python script (wrapped in undo block)
  GET  /errors   — Read Error DAT table
  GET  /operator — Get operator info
  GET  /health   — Health check

Setup:
  1. Create a WebServer DAT, set Port to 9980, Active to On
  2. Create a Text DAT, paste this script into it
  3. Set the WebServer DAT's Callbacks DAT to point to this Text DAT
  4. Create an Error DAT (name it 'error1') to capture Python errors
"""

import json
import io
import sys


def onHTTPRequest(webServerDAT, request, response):
    """Handle incoming HTTP requests from the MCP server."""
    uri = request['uri']
    method = request['method']

    if uri == '/health':
        response['statusCode'] = 200
        response['statusReason'] = 'OK'
        response['data'] = json.dumps({'status': 'ok', 'project': project.name})
        return response

    if uri == '/execute' and method == 'POST':
        return _handle_execute(request, response)

    if uri == '/errors' and method == 'GET':
        return _handle_errors(response)

    if uri.startswith('/operator') and method == 'GET':
        return _handle_operator(request, response)

    if uri.startswith('/chop') and method == 'GET':
        return _handle_chop(request, response)

    if uri.startswith('/screenshot') and method == 'GET':
        return _handle_screenshot(request, response)

    if uri.startswith('/image_stats') and method == 'GET':
        return _handle_image_stats(request, response)

    # Unknown endpoint
    response['statusCode'] = 404
    response['statusReason'] = 'Not Found'
    response['data'] = json.dumps({'error': f'Unknown endpoint: {method} {uri}'})
    return response


def _handle_execute(request, response):
    """Execute a Python script wrapped in an undo block."""
    result = {'output': '', 'errors': []}

    try:
        body = request.get('data', b'')
        if isinstance(body, bytes):
            body = body.decode('utf-8')
        payload = json.loads(body)
        script = payload.get('script', '')
        undo_label = payload.get('undo_label', 'MCP Script')
    except Exception as e:
        result['errors'].append(f'Failed to parse request: {e}')
        response['statusCode'] = 400
        response['data'] = json.dumps(result)
        return response

    # Capture stdout
    buf = io.StringIO()
    old_stdout = sys.stdout

    try:
        # Wrap in undo block
        ui.undo.startBlock(undo_label)
        sys.stdout = buf
        exec(script)
        sys.stdout = old_stdout
        ui.undo.endBlock()
        result['output'] = buf.getvalue()
    except Exception as e:
        sys.stdout = old_stdout
        try:
            ui.undo.endBlock()
        except:
            pass
        result['errors'].append(str(e))

    # Also read errors from the Error DAT
    error_dat = op('error1')
    if error_dat and error_dat.numRows > 1:
        for row in range(1, error_dat.numRows):
            try:
                err_entry = {
                    'type': str(error_dat[row, 'type'].val) if error_dat.numCols > 0 else '',
                    'absFrame': str(error_dat[row, 'absFrame'].val) if error_dat.numCols > 1 else '',
                    'text': str(error_dat[row, 'text'].val) if error_dat.numCols > 2 else '',
                }
                result['errors'].append(err_entry)
            except:
                pass

    response['statusCode'] = 200
    response['statusReason'] = 'OK'
    response['data'] = json.dumps(result)
    return response


def _handle_errors(response):
    """Read the Error DAT table."""
    errors = []
    error_dat = op('error1')
    if error_dat and error_dat.numRows > 1:
        for row in range(1, error_dat.numRows):
            try:
                err_entry = {
                    'type': str(error_dat[row, 0].val),
                    'absFrame': str(error_dat[row, 1].val) if error_dat.numCols > 1 else '',
                    'text': str(error_dat[row, 2].val) if error_dat.numCols > 2 else '',
                }
                errors.append(err_entry)
            except:
                pass

    response['statusCode'] = 200
    response['statusReason'] = 'OK'
    response['data'] = json.dumps({'errors': errors})
    return response


def _handle_chop(request, response):
    """Return all channel values from a CHOP. Query param: ?path=/ascii_UI"""
    uri = request['uri']
    path = '/ascii_UI'
    if '?path=' in uri:
        from urllib.parse import unquote
        path = unquote(uri.split('?path=')[1])

    target = op(path)
    if target is None:
        response['statusCode'] = 404
        response['data'] = json.dumps({'error': f'Operator not found: {path}'})
        return response

    if target.family != 'CHOP':
        response['statusCode'] = 400
        response['data'] = json.dumps({'error': f'{path} is not a CHOP (family: {target.family})'})
        return response

    channels = {}
    for chan in target.chans():
        channels[chan.name] = chan[0]  # current sample value

    response['statusCode'] = 200
    response['statusReason'] = 'OK'
    response['data'] = json.dumps({
        'path': target.path,
        'name': target.name,
        'numSamples': target.numSamples,
        'rate': target.rate,
        'channels': channels,
    })
    return response


def _handle_screenshot(request, response):
    """Save a TOP as PNG and return it as base64. Query params: ?path=/project1/out1&save_dir=C:/..."""
    import base64
    import os
    import tempfile
    from urllib.parse import unquote, parse_qs, urlparse

    uri = request['uri']
    parsed = urlparse(uri)
    params = parse_qs(parsed.query)

    op_path = unquote(params.get('path', ['/project1/out1'])[0])
    save_dir = unquote(params.get('save_dir', ['C:/Users/nik/Documents/AI/TD MCP/screenshots'])[0])

    target = op(op_path)
    if target is None:
        response['statusCode'] = 404
        response['data'] = json.dumps({'error': f'Operator not found: {op_path}'})
        return response

    if target.family != 'TOP':
        response['statusCode'] = 400
        response['data'] = json.dumps({'error': f'{op_path} is not a TOP (family: {target.family})'})
        return response

    try:
        os.makedirs(save_dir, exist_ok=True)
        import time
        filename = f'td_screenshot_{int(time.time()*1000)}.png'
        filepath = os.path.join(save_dir, filename).replace('\\', '/')
        target.save(filepath)
        with open(filepath, 'rb') as f:
            img_b64 = base64.b64encode(f.read()).decode('utf-8')
        response['statusCode'] = 200
        response['statusReason'] = 'OK'
        response['data'] = json.dumps({
            'path': op_path,
            'saved_to': filepath,
            'image_b64': img_b64,
            'mime_type': 'image/png',
        })
    except Exception as e:
        response['statusCode'] = 500
        response['data'] = json.dumps({'error': str(e)})
    return response


def _handle_image_stats(request, response):
    """
    Read row-average and column-average CHOPs and return per-row/col R,G,B,A values
    plus aggregate stats (mean, min, max per channel).

    Query params:
      ?rows_chop=/path/to/rows_chop   (CHOP with channels r,g,b,a — one sample per row)
      ?cols_chop=/path/to/cols_chop   (CHOP with channels r,g,b,a — one sample per col)

    Channels are identified by containing 'r','g','b','a' in their name (case-insensitive).
    """
    from urllib.parse import unquote, parse_qs, urlparse

    uri = request['uri']
    parsed = urlparse(uri)
    params = parse_qs(parsed.query)

    rows_path = unquote(params.get('rows_chop', [''])[0])
    cols_path = unquote(params.get('cols_chop', [''])[0])

    if not rows_path or not cols_path:
        response['statusCode'] = 400
        response['data'] = json.dumps({'error': 'rows_chop and cols_chop query params required'})
        return response

    def read_chop_rgba(chop_path):
        """Read r,g,b,a channels from a CHOP, return list of {r,g,b,a} per sample."""
        target = op(chop_path)
        if target is None:
            return None, f'Operator not found: {chop_path}'
        if target.family != 'CHOP':
            return None, f'{chop_path} is not a CHOP'

        # Find channels by matching name suffix/content
        chan_map = {}
        for chan in target.chans():
            n = chan.name.lower()
            for label in ('r', 'g', 'b', 'a'):
                if n == label or n.endswith(label) or n.endswith(f'_{label}') or n.endswith(f'.{label}'):
                    chan_map[label] = chan
                    break

        # Fall back: assign by index order r,g,b,a if names don't match
        if len(chan_map) < 4:
            all_chans = target.chans()
            for i, label in enumerate(['r', 'g', 'b', 'a']):
                if label not in chan_map and i < len(all_chans):
                    chan_map[label] = all_chans[i]

        num_samples = target.numSamples
        samples = []
        for s in range(num_samples):
            samples.append({
                'r': float(chan_map['r'][s]) if 'r' in chan_map else 0.0,
                'g': float(chan_map['g'][s]) if 'g' in chan_map else 0.0,
                'b': float(chan_map['b'][s]) if 'b' in chan_map else 0.0,
                'a': float(chan_map['a'][s]) if 'a' in chan_map else 1.0,
            })
        return samples, None

    def aggregate(samples):
        if not samples:
            return {}
        result = {}
        for ch in ('r', 'g', 'b', 'a'):
            vals = [s[ch] for s in samples]
            result[ch] = {
                'mean': sum(vals) / len(vals),
                'min': min(vals),
                'max': max(vals),
            }
        # Luminance (perceptual)
        lum = [0.2126 * s['r'] + 0.7152 * s['g'] + 0.0722 * s['b'] for s in samples]
        result['luminance'] = {
            'mean': sum(lum) / len(lum),
            'min': min(lum),
            'max': max(lum),
        }
        return result

    rows_samples, rows_err = read_chop_rgba(rows_path)
    if rows_err:
        response['statusCode'] = 404
        response['data'] = json.dumps({'error': rows_err})
        return response

    cols_samples, cols_err = read_chop_rgba(cols_path)
    if cols_err:
        response['statusCode'] = 404
        response['data'] = json.dumps({'error': cols_err})
        return response

    rows_agg = aggregate(rows_samples)
    cols_agg = aggregate(cols_samples)

    # Overall stats: average of rows and cols aggregates
    overall = {}
    for ch in ('r', 'g', 'b', 'a', 'luminance'):
        overall[ch] = {
            'mean': (rows_agg[ch]['mean'] + cols_agg[ch]['mean']) / 2,
            'min': min(rows_agg[ch]['min'], cols_agg[ch]['min']),
            'max': max(rows_agg[ch]['max'], cols_agg[ch]['max']),
        }

    response['statusCode'] = 200
    response['statusReason'] = 'OK'
    response['data'] = json.dumps({
        'rows': {'samples': rows_samples, 'aggregate': rows_agg},
        'cols': {'samples': cols_samples, 'aggregate': cols_agg},
        'overall': overall,
    })
    return response


def _handle_operator(request, response):
    """Get operator info."""
    uri = request['uri']
    path = '/'
    if '?path=' in uri:
        path = uri.split('?path=')[1]
        from urllib.parse import unquote
        path = unquote(path)

    target = op(path)
    if target is None:
        response['statusCode'] = 404
        response['data'] = json.dumps({'error': f'Operator not found: {path}'})
        return response

    info = {
        'path': target.path,
        'name': target.name,
        'type': target.OPType,
        'family': target.family,
    }

    response['statusCode'] = 200
    response['statusReason'] = 'OK'
    response['data'] = json.dumps(info)
    return response
