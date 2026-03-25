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
