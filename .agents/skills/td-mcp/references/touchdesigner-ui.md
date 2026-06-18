# TouchDesigner UI Patterns

Use Basic Widgets palette components, not bare `sliderCOMP` or `buttonCOMP`. Bare slider/button COMPs tend to render as tiny low-contrast nubs and are not the intended styled widget surface.

Derive the widget palette path at runtime:

```python
import os
bw = os.path.join(app.installFolder, "Samples/Palette/UI/Basic Widgets")
```

Common widget `.tox` files include `sliderHorz.tox`, `sliderVert.tox`, `buttonMomentary.tox`, `buttonToggle.tox`, `knobFixed.tox`, `fieldString.tox`, `float1.tox`, and `dropDownMenu.tox`.

Instantiate widgets programmatically. `loadTox` lands the tox as a child wrapped in packaging containers, so create a temporary holder, load the tox, find the native `widget` operator iteratively, copy it into the real parent, then destroy the holder.

```python
parent_comp = op('/project1/cont_uidemo')
holder = parent_comp.create(containerCOMP, '__tmp')
holder.loadTox(os.path.join(bw, 'sliderHorz.tox'))

widget_op = None
stack = list(holder.children)
while stack:
    o = stack.pop()
    if o.type == 'widget':
        widget_op = o
        break
    stack.extend(o.children)

w = parent_comp.copyOPs([widget_op])[0]
holder.destroy()
w.name = 'slider_period'
```

Widget controls expose `Value0`, `Widgetlabel`, and styling parameters such as `Sliderbgcolor*`, `Sliderknobcolor*`, `Sliderindicatorcolor*`, `Labelfontcolor*`, `Rollovercolor*`, `Font`, and `Fontfile`. TOP-valued styling parameters such as `Sliderbgtop` and `Sliderknobtop` can provide non-flat looks.

For parameter wiring:

```python
t.par.X.bindExpr = "op('slider_period').par.Value0"
t.par.X.mode = ParMode.BIND
```

For logic on change or pulse, create a Parameter Execute DAT watching the widget and implement `onValueChange` or `onPulse`.

Panel coordinates use a bottom-left origin. `(0, 0)` is the bottom-left corner and `y` grows upward. Parent `align='none'` lets children use their own `x` and `y`; layout modes auto-arrange children and ignore child positions.

A container only shows panel UI when its panel is displayed. Use `comp.viewer = True`, `comp.openViewer(unique=True, borders=True)`, a `windowCOMP`, the Perform window targeting the container, or a displayed ancestor. `viewer` is an operator attribute, not a parameter.

`take_screenshot` captures TOP output only and cannot directly capture panel UI. Verify panels through operator parameters, viewer state, window targeting, or by asking the user to glance at the viewer when necessary.
