import numpy as np

def onSetupParameters(scriptOp):
    return

def onPulse(par):
    return

def onCook(scriptOp):
    st = parent().fetch('colormask_stencil', None)
    if st is None:
        arr = np.zeros((1, 1, 4), dtype=np.float32)
        arr[..., 3] = 1.0
    else:
        arr = np.zeros((st['h'], st['w'], 4), dtype=np.float32)
        arr[..., 0] = st['data'].astype(np.float32) / 255.0
        arr[..., 3] = 1.0
    scriptOp.copyNumpyArray(arr)
    return

