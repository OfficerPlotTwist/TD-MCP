# OptiTrack Camera Controls (OSC) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the live TouchDesigner project set OptiTrack camera exposure, IR intensity, frame rate, and imager gain on all streaming cameras via OSC-over-UDP, while video streams over Spout.

**Architecture:** Add a one-way OSC/UDP control channel. A new C++ module in `optitrack_spout` binds a non-blocking UDP socket, parses OSC, and applies clamped values to every streaming camera between frames. A TD container sends OSC from four widgets via an OSC Out CHOP.

**Tech Stack:** C++17, Winsock2 (UDP), OptiTrack Camera SDK 3.4.x, CMake/VS2022; TouchDesigner (Basic Widgets, Constant CHOP, OSC Out CHOP), Python over the MCP bridge.

## Global Constraints

- Repo (app): `C:\Users\NICKESCHEN\dev\opti-hacking`, branch off `main`. Build: `cmake --build build --config Release --target <t>`.
- Stop any running `optitrack_spout.exe` before building (linker can't overwrite a running exe).
- No new third-party dependencies; OSC parsed by hand. Winsock only.
- Controls **on by default**, port **7400**, `--control-port 0` disables. Never break the existing stream path when TD is absent.
- OSC addresses: `/cam/exposure`, `/cam/intensity`, `/cam/framerate`, `/cam/gain` (one int/float arg).
- App must **clamp** every value to the camera's SDK min/max; malformed packets ignored; bind failure warns and continues streaming.
- TD: `git`/bridge conventions from CLAUDE.md — Basic Widgets, lift native `widget` op, iterative tree walk, containers only render when displayed.

---

### Task 1: OSC parser + UDP receiver module

**Files:**
- Create: `src/osc_control.h`
- Create: `src/osc_control.cpp`
- Test: `src/osc_control_test.cpp`
- Modify: `CMakeLists.txt` (add `osc_control.cpp` to `optitrack_spout`; add `osc_control_test` target)

**Interfaces:**
- Produces:
  - `struct ControlValues { std::optional<int> exposure, intensity, framerate, gainLevel; };`
  - `int oscParseDatagram(const uint8_t* data, int len, ControlValues& out);` — parses one UDP datagram (single OSC message or `#bundle`), sets addressed fields, returns count of recognized control messages.
  - `class OscControlReceiver { bool open(uint16_t port); bool poll(ControlValues& out); void close(); ~OscControlReceiver(); };`

- [ ] **Step 1: Write the failing test** — `src/osc_control_test.cpp`

```cpp
// Standalone unit test for the OSC parser (no hardware, no sockets).
#include "osc_control.h"
#include <cstdio>
#include <cstring>
#include <cstdint>
#include <vector>

static int g_fail = 0;
#define CHECK(c) do { if(!(c)) { std::printf("FAIL %s:%d  %s\n", __FILE__, __LINE__, #c); ++g_fail; } } while(0)

// Build one OSC message: address + ",i" + big-endian int arg (4-byte padded).
static std::vector<uint8_t> msgInt(const char* addr, int32_t v) {
    std::vector<uint8_t> b;
    auto pushStr = [&](const char* s){ int n=(int)std::strlen(s)+1; for(int i=0;i<n;i++) b.push_back((uint8_t)s[i]); while(b.size()&3) b.push_back(0); };
    pushStr(addr);
    pushStr(",i");
    b.push_back((v>>24)&0xff); b.push_back((v>>16)&0xff); b.push_back((v>>8)&0xff); b.push_back(v&0xff);
    return b;
}

int main() {
    // exposure int message
    { ControlValues cv; auto m = msgInt("/cam/exposure", 250);
      int n = oscParseDatagram(m.data(), (int)m.size(), cv);
      CHECK(n == 1); CHECK(cv.exposure.has_value() && *cv.exposure == 250);
      CHECK(!cv.intensity.has_value()); }

    // float arg rounds to int
    { ControlValues cv; std::vector<uint8_t> b;
      auto pushStr=[&](const char* s){int n=(int)std::strlen(s)+1;for(int i=0;i<n;i++)b.push_back((uint8_t)s[i]);while(b.size()&3)b.push_back(0);};
      pushStr("/cam/framerate"); pushStr(",f");
      float f=119.6f; uint32_t u; std::memcpy(&u,&f,4);
      b.push_back((u>>24)&0xff);b.push_back((u>>16)&0xff);b.push_back((u>>8)&0xff);b.push_back(u&0xff);
      ControlValues cv2; int n=oscParseDatagram(b.data(),(int)b.size(),cv2);
      CHECK(n==1); CHECK(cv2.framerate.has_value() && *cv2.framerate==120); }

    // unknown address ignored
    { ControlValues cv; auto m = msgInt("/cam/nope", 5);
      int n = oscParseDatagram(m.data(), (int)m.size(), cv);
      CHECK(n == 0); CHECK(!cv.exposure.has_value()); }

    // bundle of two messages
    { auto a = msgInt("/cam/intensity", 12); auto c = msgInt("/cam/gain", 2);
      std::vector<uint8_t> b; const char* hdr="#bundle";
      for(int i=0;i<8;i++) b.push_back((uint8_t)(i<7?hdr[i]:0));
      for(int i=0;i<8;i++) b.push_back(i==7?1:0);          // timetag "immediately"
      auto pushElem=[&](std::vector<uint8_t>& e){ int32_t s=(int32_t)e.size(); b.push_back((s>>24)&0xff);b.push_back((s>>16)&0xff);b.push_back((s>>8)&0xff);b.push_back(s&0xff); for(uint8_t x:e) b.push_back(x); };
      pushElem(a); pushElem(c);
      ControlValues cv; int n=oscParseDatagram(b.data(),(int)b.size(),cv);
      CHECK(n==2); CHECK(*cv.intensity==12); CHECK(*cv.gainLevel==2); }

    // truncated/garbage does not crash and yields nothing
    { ControlValues cv; uint8_t junk[3]={'/','c','a'}; int n=oscParseDatagram(junk,3,cv); CHECK(n==0); }

    std::printf(g_fail? "TESTS FAILED (%d)\n" : "ALL TESTS PASSED\n", g_fail);
    return g_fail ? 1 : 0;
}
```

- [ ] **Step 2: Add header** — `src/osc_control.h`

```cpp
#pragma once
#include <cstdint>
#include <optional>

// One-way OSC-over-UDP control values for camera imaging settings.
// Only fields that arrived are set.
struct ControlValues {
    std::optional<int> exposure;
    std::optional<int> intensity;
    std::optional<int> framerate;
    std::optional<int> gainLevel;
};

// Parse a single UDP datagram (one OSC message OR a #bundle of messages) into `out`,
// setting only the controls addressed. Returns count of recognized control messages.
// Pure function — unit-testable, no sockets.
int oscParseDatagram(const uint8_t* data, int len, ControlValues& out);

// Non-blocking UDP receiver bound to 127.0.0.1:port. Header pulls in NO winsock so it
// is safe to include after <windows.h> in main_camera.cpp.
class OscControlReceiver {
public:
    ~OscControlReceiver();
    bool open(uint16_t port);      // bind + non-blocking; false on failure
    bool poll(ControlValues& out); // drain socket; true if any control parsed
    void close();
private:
    uintptr_t sock_ = ~uintptr_t(0);
    bool wsaInit_ = false;
};
```

- [ ] **Step 3: Implement** — `src/osc_control.cpp`

```cpp
#include "osc_control.h"
#include <winsock2.h>
#include <ws2tcpip.h>
#include <cstring>
#include <cmath>
#pragma comment(lib, "Ws2_32.lib")

static int32_t beI32(const uint8_t* p) {
    return (int32_t)(((uint32_t)p[0]<<24)|((uint32_t)p[1]<<16)|((uint32_t)p[2]<<8)|(uint32_t)p[3]);
}
static float beF32(const uint8_t* p) {
    uint32_t u = ((uint32_t)p[0]<<24)|((uint32_t)p[1]<<16)|((uint32_t)p[2]<<8)|(uint32_t)p[3];
    float f; std::memcpy(&f,&u,4); return f;
}
static int padded(int n) { return (n + 4) & ~3; }
// length of an OSC string (incl NUL, padded to 4) within [0,len); -1 if no terminator.
static int oscStrLen(const uint8_t* p, int len) {
    int i = 0; while (i < len && p[i] != 0) ++i;
    if (i >= len) return -1;
    return padded(i + 1);
}

static int parseMessage(const uint8_t* p, int len, ControlValues& out) {
    int a = oscStrLen(p, len); if (a < 0) return 0;
    const char* addr = (const char*)p;
    int off = a; if (off >= len || p[off] != ',') return 0;
    int t = oscStrLen(p + off, len - off); if (t < 0) return 0;
    char tag = (char)p[off + 1];
    int argOff = off + t;
    int val;
    if (tag == 'i') { if (argOff + 4 > len) return 0; val = beI32(p + argOff); }
    else if (tag == 'f') { if (argOff + 4 > len) return 0; val = (int)std::lround(beF32(p + argOff)); }
    else return 0;
    if (std::strcmp(addr, "/cam/exposure")  == 0) { out.exposure  = val; return 1; }
    if (std::strcmp(addr, "/cam/intensity") == 0) { out.intensity = val; return 1; }
    if (std::strcmp(addr, "/cam/framerate") == 0) { out.framerate = val; return 1; }
    if (std::strcmp(addr, "/cam/gain")      == 0) { out.gainLevel = val; return 1; }
    return 0;
}

int oscParseDatagram(const uint8_t* data, int len, ControlValues& out) {
    if (len >= 8 && std::memcmp(data, "#bundle", 8) == 0) {
        int off = 16; int count = 0;                 // 8 "#bundle\0" + 8 timetag
        while (off + 4 <= len) {
            int32_t sz = beI32(data + off); off += 4;
            if (sz < 0 || off + sz > len) break;
            count += parseMessage(data + off, sz, out);
            off += sz;
        }
        return count;
    }
    return parseMessage(data, len, out);
}

OscControlReceiver::~OscControlReceiver() { close(); }

bool OscControlReceiver::open(uint16_t port) {
    WSADATA w; if (WSAStartup(MAKEWORD(2,2), &w) != 0) return false; wsaInit_ = true;
    SOCKET s = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
    if (s == INVALID_SOCKET) return false;
    sockaddr_in a{}; a.sin_family = AF_INET; a.sin_port = htons(port);
    inet_pton(AF_INET, "127.0.0.1", &a.sin_addr);
    if (bind(s, (sockaddr*)&a, sizeof(a)) == SOCKET_ERROR) { closesocket(s); return false; }
    u_long nb = 1; ioctlsocket(s, FIONBIO, &nb);
    sock_ = (uintptr_t)s;
    return true;
}

bool OscControlReceiver::poll(ControlValues& out) {
    if (sock_ == ~uintptr_t(0)) return false;
    uint8_t buf[2048]; bool any = false;
    for (;;) {
        int n = recvfrom((SOCKET)sock_, (char*)buf, sizeof(buf), 0, nullptr, nullptr);
        if (n <= 0) break;
        if (oscParseDatagram(buf, n, out) > 0) any = true;
    }
    return any;
}

void OscControlReceiver::close() {
    if (sock_ != ~uintptr_t(0)) { closesocket((SOCKET)sock_); sock_ = ~uintptr_t(0); }
    if (wsaInit_) { WSACleanup(); wsaInit_ = false; }
}
```

- [ ] **Step 4: Wire CMake** — in `CMakeLists.txt`, add `src/osc_control.cpp` to the `optitrack_spout` target's sources, and add a test target near the other targets:

```cmake
# OSC parser unit test (no hardware, no SDK)
add_executable(osc_control_test src/osc_control_test.cpp src/osc_control.cpp)
target_compile_features(osc_control_test PRIVATE cxx_std_17)
```

- [ ] **Step 5: Build the test and run it (fails first if impl missing, then passes)**

Run:
```
cmake -S . -B build -G "Visual Studio 17 2022" -A x64 -DCAMERA_SDK_DIR="C:/Program Files (x86)/OptiTrack/CameraSDK"
cmake --build build --config Release --target osc_control_test
build/Release/osc_control_test.exe
```
Expected: `ALL TESTS PASSED` (exit 0).

- [ ] **Step 6: Commit**

```
git checkout -b feat/camera-controls-osc
git add src/osc_control.h src/osc_control.cpp src/osc_control_test.cpp CMakeLists.txt
git commit -m "feat(control): OSC/UDP receiver + parser for camera settings (unit-tested)"
```

---

### Task 2: Wire controls into the streaming loop

**Files:**
- Modify: `src/main_camera.cpp` (arg parse; receiver open; apply-on-change in the stream loop)

**Interfaces:**
- Consumes: `ControlValues`, `OscControlReceiver` from Task 1.
- Produces: `--control-port <n>` behavior; clamped live application to all `streams`.

- [ ] **Step 1: Include the module** — add near the top includes of `src/main_camera.cpp`:

```cpp
#include "osc_control.h"
```

- [ ] **Step 2: Add the flag** — add `int controlPort = 7400;` beside the other locals, and a parse branch in the arg loop (next to `--mode`):

```cpp
} else if (std::strcmp(argv[i], "--control-port") == 0 && i + 1 < argc) {
    controlPort = (int)strtol(argv[++i], nullptr, 10);
```

- [ ] **Step 3: Add clamp + apply helpers** — above `int main(...)`:

```cpp
static int clampi(int v, int lo, int hi) { return v < lo ? lo : (v > hi ? hi : v); }

// Apply only the controls that changed vs `applied`, to every streaming camera,
// clamped to each camera's real SDK limits. Updates `applied`.
static void applyControls(const ControlValues& cv,
                          std::vector<std::unique_ptr<CamStream>>& streams,
                          ControlValues& applied) {
    for (auto& cs : streams) {
        Camera* c = cs->cam.get();
        if (cv.exposure  && cv.exposure  != applied.exposure)
            c->SetExposure(clampi(*cv.exposure,  c->MinimumExposureValue(),  c->MaximumExposureValue()));
        if (cv.intensity && cv.intensity != applied.intensity)
            c->SetIntensity(clampi(*cv.intensity, c->MinimumIntensity(),      c->MaximumIntensity()));
        if (cv.framerate && cv.framerate != applied.framerate)
            c->SetFrameRate(clampi(*cv.framerate, c->MinimumFrameRateValue(), c->MaximumFrameRateValue()));
        if (cv.gainLevel && cv.gainLevel != applied.gainLevel)
            c->SetImagerGain((eImagerGain)clampi(*cv.gainLevel, 0, c->ImagerGainLevels() - 1));
    }
    if (cv.exposure)  applied.exposure  = cv.exposure;
    if (cv.intensity) applied.intensity = cv.intensity;
    if (cv.framerate) applied.framerate = cv.framerate;
    if (cv.gainLevel) applied.gainLevel = cv.gainLevel;
}
```

Note: `eImagerGain` is the SDK enum (from `camera.h`, in scope via `using namespace CameraLibrary;`). If the compiler reports it unscoped, qualify as `Camera::eImagerGain`.

- [ ] **Step 4: Open the receiver before the stream loop** — after the "Streaming N camera(s)" print, before `while (g_run)`:

```cpp
OscControlReceiver control;
ControlValues applied;
if (controlPort > 0) {
    if (control.open((uint16_t)controlPort))
        std::printf("Control: listening for OSC on 127.0.0.1:%d (/cam/{exposure,intensity,framerate,gain})\n", controlPort);
    else
        std::fprintf(stderr, "WARN: could not bind control port %d; camera controls disabled.\n", controlPort);
    std::fflush(stdout);
}
```

- [ ] **Step 5: Poll + apply inside the loop** — at the top of the `while (g_run)` body, before the per-camera frame work:

```cpp
if (controlPort > 0) {
    ControlValues cv;
    if (control.poll(cv)) applyControls(cv, streams, applied);
}
```

- [ ] **Step 6: Build (stop any running exe first)**

Run:
```
powershell -Command "Get-Process optitrack_spout -EA SilentlyContinue | Stop-Process"
cmake --build build --config Release --target optitrack_spout
```
Expected: build succeeds, `optitrack_spout.exe` produced.

- [ ] **Step 7: Manual smoke test** — start the sender (Motive closed), confirm the control line prints and streaming is unaffected:

Run:
```
build/Release/optitrack_spout.exe --list
build/Release/optitrack_spout.exe
```
Expected: `--list` shows the camera; streaming prints `Control: listening for OSC on 127.0.0.1:7400 ...` and the sender runs normally. Ctrl+C to stop.

- [ ] **Step 8: Commit**

```
git add src/main_camera.cpp
git commit -m "feat(control): apply OSC camera settings to all streaming cameras (clamped)"
```

---

### Task 3: TouchDesigner control panel

**Files:**
- No repo files — builds ops in the live TD project via `execute_script` over the MCP bridge.

**Interfaces:**
- Consumes: the app's OSC contract (`127.0.0.1:7400`, `/cam/...`).
- Produces: `/project1/cont_cam_controls` (displayed) with 4 controls → `Constant CHOP cam_values` → `OSC Out CHOP oscout_cam`.

- [ ] **Step 1: Save a checkpoint of /project1 before building UI** (bulk op safety per CLAUDE.md)

Use `save_checkpoint` on `/project1`.

- [ ] **Step 2: Build the panel** — run this via `execute_script`:

```python
import os
proj = op('/project1')
bw = os.path.join(app.installFolder, "Samples/Palette/UI/Basic Widgets")

cont = op('/project1/cont_cam_controls') or proj.create(containerCOMP, 'cont_cam_controls')
cont.nodeX, cont.nodeY = -1400, 400
cont.par.align = 'lefttoright' if hasattr(cont.par,'align') else cont.par.align

def load_widget(parent, tox, newname):
    ex = parent.op(newname)
    if ex: return ex
    holder = parent.create(containerCOMP, '__tmp')
    holder.loadTox(os.path.join(bw, tox))
    w = None; stack = list(holder.children)
    while stack:
        o = stack.pop()
        if o.type == 'widget': w = o; break
        stack.extend(o.children)
    out = parent.copyOPs([w])[0]
    holder.destroy()
    out.name = newname
    return out

s_exp  = load_widget(cont, 'sliderHorz.tox',   'slider_exposure')
s_int  = load_widget(cont, 'sliderHorz.tox',   'slider_intensity')
s_fps  = load_widget(cont, 'sliderHorz.tox',   'slider_framerate')
m_gain = load_widget(cont, 'dropDownMenu.tox', 'menu_gain')

for w,(lbl,y) in {s_exp:('Exposure',360), s_int:('IR Intensity',280),
                  s_fps:('Frame Rate',200), m_gain:('Gain',120)}.items():
    w.par.w, w.par.h = 300, 60
    w.par.x, w.par.y = 40, y
    if hasattr(w.par,'Widgetlabel'): w.par.Widgetlabel = lbl

# Constant CHOP: normalized widget Value0 -> real units, one channel per control.
cv = op('/project1/cont_cam_controls/cam_values') or cont.create(constantCHOP, 'cam_values')
cv.nodeX, cv.nodeY = 400, 0
rows = [('exposure',  "op('slider_exposure').par.Value0*(500-1)+1"),
        ('intensity', "op('slider_intensity').par.Value0*15"),
        ('framerate', "op('slider_framerate').par.Value0*(240-30)+30"),
        ('gain',      "op('menu_gain').par.Value0")]
# ensure enough constant slots
if hasattr(cv.par,'const0name'):
    for idx,(nm,expr) in enumerate(rows):
        getattr(cv.par, f'const{idx}name').val = nm
        getattr(cv.par, f'const{idx}value').expr = expr
    # blank any extra default rows
    i = len(rows)
    while hasattr(cv.par, f'const{i}name'):
        getattr(cv.par, f'const{i}name').val = ''
        i += 1

osc = op('/project1/cont_cam_controls/oscout_cam') or cont.create(oscoutCHOP, 'oscout_cam')
osc.nodeX, osc.nodeY = 600, 0
osc.inputConnectors[0].connect(cv)
osc.par.netaddress = '127.0.0.1'
osc.par.port = 7400
if hasattr(osc.par,'address'): osc.par.address = '/cam'
if hasattr(osc.par,'bundle'): osc.par.bundle = False
if hasattr(osc.par,'sendonchange'): osc.par.sendonchange = True

cont.viewer = True
print('panel built:', [c.name for c in cont.children])
```

- [ ] **Step 3: Verify structure** — via `get_operator_info` / `get_par_value`:

Confirm `/project1/cont_cam_controls` has children `slider_exposure, slider_intensity, slider_framerate, menu_gain, cam_values, oscout_cam`; `oscout_cam.port == 7400`, `netaddress == '127.0.0.1'`; `cam_values` has 4 channels named exposure/intensity/framerate/gain. Read `cam_values` values change when you set a slider's `Value0`.

- [ ] **Step 4: Display the panel** — open a floating viewer so it's visible:

```python
op('/project1/cont_cam_controls').openViewer(unique=True, borders=True)
```

- [ ] **Step 5: Save** — persist the TD project after verification:

Use `execute_script("project.save()")` (per bridge save discipline). If the project is untitled and `save()` would hang, use `save_checkpoint` instead.

---

### Task 4: End-to-end verification

**Files:** none.

- [ ] **Step 1: Start the sender** (Motive closed):

```
C:\Users\NICKESCHEN\dev\opti-hacking\build\Release\optitrack_spout.exe
```
Expected: streams the camera and prints the `Control: listening ...` line.

- [ ] **Step 2: Drive exposure from TD** — set the exposure slider high, then low. In TD, force-cook `/project1/spoutin_optitrack` and sample pixels:

```python
t = op('/project1/spoutin_optitrack'); t.cook(force=True)
a = t.numpyArray(delayed=False)
print('mean brightness:', None if a is None else float(a.mean()))
```
Expected: mean brightness rises with higher exposure and falls with lower — proving the value reached the camera.

- [ ] **Step 3: Drive IR intensity** — change the intensity slider; confirm marker/highlight brightness changes in the sampled image; confirm the sender never drops the stream and does not crash.

- [ ] **Step 4: Regression** — stop TD's OSC (or leave the panel idle) and confirm the sender keeps streaming; run `optitrack_spout.exe --control-port 0` and confirm controls are disabled but streaming still works.

- [ ] **Step 5: Final commit / PR** — push the app branch and open a PR:

```
git push -u origin feat/camera-controls-osc
```
Open a PR against `main` summarizing the OSC control channel.

---

## Self-Review

- **Spec coverage:** control set (exposure/intensity/framerate/gain) → Tasks 2/3; all-cameras scope → `applyControls` loops all `streams`; OSC channel + port 7400 → Tasks 1–3; no-readback + clamp → `applyControls`; fixed TD ranges → Task 3 expressions; error handling (bind fail, malformed) → Tasks 1/2; verification → Task 4. Covered.
- **Placeholder scan:** none — all code and commands are concrete.
- **Type consistency:** `ControlValues`, `oscParseDatagram`, `OscControlReceiver::{open,poll,close}`, `applyControls`, `clampi`, `eImagerGain` used consistently across tasks.
