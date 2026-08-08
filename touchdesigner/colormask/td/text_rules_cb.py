import numpy as np

def onSetupParameters(scriptOp):
    return

def onPulse(par):
    return

def onCook(scriptOp):
    rules = parent().fetch('colormask_rules', [])
    n = max(1, len(rules))
    arr = np.zeros((1, n, 4), dtype=np.float32)
    if not rules:
        arr[0, 0, 3] = -1.0
    else:
        for i in range(len(rules)):
            t, r, g, b, tol = rules[i]
            arr[0, i, 0] = r
            arr[0, i, 1] = g
            arr[0, i, 2] = b
            arr[0, i, 3] = tol + (10.0 if t == 1 else 0.0)
    scriptOp.copyNumpyArray(arr)
    return

