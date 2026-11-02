"""Run inside TouchDesigner to install a portable, inactive TD_MCP component.

In the TD Textport:
    ns = {'__file__': '/path/to/repo/touchdesigner/install_bridge.py'}
    exec(compile(open(ns['__file__'], encoding='utf-8').read(), ns['__file__'], 'exec'), ns)
    bridge = ns['install_bridge'](op('/project1'))

Inspect the component, save your project, then activate its webserver manually.
The callback source is embedded; the installed component needs no repo path.
"""
from pathlib import Path


def install_bridge(parent_comp, name='TD_MCP', port=9980, callback_source=None):
    """Create a bridge without replacing existing operators or starting a server."""
    if not name or '/' in name or parent_comp.op(name) is not None:
        raise ValueError('Choose an unused child component name')
    port = int(port)
    if not 1 <= port <= 65535:
        raise ValueError('Port must be between 1 and 65535')
    if callback_source is None:
        callback_source = Path(__file__).with_name('webserver_callbacks.py').read_text(encoding='utf-8')
    compile(callback_source, '<TD_MCP callbacks>', 'exec')
    comp = parent_comp.create('baseCOMP', name)
    try:
        comp.nodeX = max([child.nodeX for child in parent_comp.children if child != comp] or [0]) + 400
        comp.nodeY = 0
        callbacks = comp.create('textDAT', 'webserver_callbacks')
        callbacks.text = callback_source
        errors = comp.create('errorDAT', 'error1')
        errors.nodeX, errors.nodeY = -200, -150
        server = comp.create('webserverDAT', 'webserver')
        server.par.active = False
        server.par.port = port
        server.par.callbacks = callbacks
        server.nodeX, server.nodeY = 0, 0
        callbacks.nodeX, callbacks.nodeY = -200, 0
        readme = comp.create('textDAT', 'README')
        readme.text = ('TD MCP bridge\nEmbedded callbacks; no external project dependencies.\n'
                       'Server is inactive on installation. Activate it manually when ready.\n'
                       'Bind/firewall access to trusted local clients: this bridge executes Python.\n'
                       'Do not restart or deactivate this component through its own MCP connection.\n')
        readme.nodeX, readme.nodeY = 200, -150
        return comp
    except Exception:
        comp.destroy()
        raise
