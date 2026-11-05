# Native PDC investigation

## Result

The native parking pages can be opened in the local G80 emulator. **The PDC
vehicle/sensor visualization is not working yet.** An empty parking page is not
a successful sensor simulation, and no public PDC control has been added.

Tests used the local Lima GPU VM and its HMI container, without a physical
headunit, vehicle network, navigation maps, or real parking sensors.

## Tested build and method

- Date: 2026-11-05.
- Profile: `g80lci-m`, native output 2880 × 960.
- `Hmi8` SHA-256:
  `9913ca569bfc78eb2b6174d0660855dc324a7b261667e0b9d20bc9352308062c`.
- Evidence: shipped symbol inventory, LLVM disassembly, native runtime logs,
  read-only runtime object discovery, and captured HMI frames.
- Temporary native calls were dispatched through the existing HMI application
  dispatcher, on the same HMI thread used by the climate/music mock.
- REA/Hopper decompilation was unavailable because Apple Events authorization
  was denied. No decompiler output or REA evidence identifiers are claimed.

All addresses below are relative to this exact executable's load base. They
are not stable APIs and must not be reused with another firmware build.

## Coding selects two different parking stacks

The initial test added the following overrides as a group:

```json
{
  "MACRO_PDC": "enabled",
  "COMMUNICATION_PARKMASTER": "gen_2021",
  "VISIBILITY_SELECTION_PARKING_PDC": "enabled",
  "VISIBILITY_SELECTION_PDC_ONLY": "enabled",
  "PDC_SOUND_ICON": "enabled"
}
```

These are experimental inputs, not a proven minimal recipe. Their enum labels
exist in the shipped coding metadata, but that does not establish complete
semantics. Absence from the user's overrides does not mean the corresponding
firmware default is disabled.

| Test | Runtime observation | Visible result |
| --- | --- | --- |
| `COMMUNICATION_PARKMASTER=gen_2021` | Modern `car::parking` service/device objects are instantiated; parkmenu backend reports `NOT_AVAILABLE`. | Native PARKING page, without the vehicle/sensor content. |
| Change to `COMMUNICATION_PARKMASTER=gen2` | Legacy `car::parkingruko` objects replace the modern ones; parking activation calls report `NOT_AVAILABLE`. | Native parking/panorama shell, without sensor content. |
| Legacy native status/distance probe | Native `isPDCActive()` changes from false to true; PDC-status and front/rear-distance callbacks return without terminating the HMI. | Parking shell remains empty; outgoing activation requests still log `PDC(false)`. |
| Add `CAMERA_SYSTEM=icam2_high` to the legacy probe | `CDevCameraProxy::init` appears; the earlier missing-camera-device errors disappear in the inspected startup log. Its service proxy still reports unavailable. | Parking shell remains empty. |

The last two rows are important: changing a local active flag and delivering
distance callbacks did **not** establish a functioning end-to-end parking
session. Likewise, loading the camera HMI adapter did not provide its backend.

## Native entry points located

### Modern parking

- `SvcParking::openParkingMainScreen()` — `0x84b4948`.
- `ParkingUtils::openCreateTaskId(long, bool, unsigned long)` — `0x84f66a0`.
- `DevParkmenuAndLayout::onRequestParkmenuAttribute(...)` — `0x847e3a0`.

Calling the page-opening helper with state `0x20700000001` and task
`0x20700000000` opens the native parking activity. Runtime activity logs report
state `519.2`; the requested state must not be assumed to be the final state.
The parkmenu/layout backend remains unavailable.

### Legacy parking

- `CSevParking::openParking()` — `0x86ecf60`.
- `OpenCloseParkingStates::openPopupCreateTaskId(...)` — `0x8706528`.
- `CDevParking::handleParkingSystemState2(...)` — `0x8654440`.
- `CDevParking::statusFunctionParking2ToMap(...)` — `0x8653cec`.
- `CDevParking::isPDCActive()` — `0x864aae0`.
- `CDevParkingPDC::statusPDCStatusFunctionAttribute_callback(...)` — `0x86681e4`.
- `CDevParkingPDC::statusPDCDistanceFront2Attribute_callback(...)` — `0x86689c8`.
- `CDevParkingPDC::statusPDCDistanceRear2Attribute_callback(...)` — `0x8668bf0`.
- `CParkPDCTile::changeState(...)` — `0x87a42d0`.

The legacy page-opening helper uses state `0x21600000002` and task
`0x21600000000`, matching the disassembled native `openParking()` path.

The bounded status/distance experiment used the native parking-map conversion
with bit zero set, a status byte of `0x30`, and eight raw distance bytes of
`64` for each front/rear callback. The active getter changed from 0 to 1.
These bytes are probe inputs, **not verified physical distances or a validated
PDC message recipe**. Sector numbering and units have not been established.

## What remains to implement

The evidence points to missing backend state, not a missing navigation database.
It does not yet prove which missing input is sufficient to unlock the complete
visualization.

1. Trace the selected parking stack's activation handshake, availability, and
   layout selection together. A page-open request alone is insufficient.
2. For the modern stack, establish the actual `RequestParkmenuStruct` ABI and
   USS/display-function inputs before constructing mock messages. It contains
   enum-wrapper objects; it is not a flat sequence of flag bytes.
3. For the legacy stack, establish the full `ParkingSystemState2` message,
   selected PDC tile, and camera/parking service state. Explain why outgoing
   activation remains `PDC(false)` despite the local active getter being true.
4. Supply repeatable distance updates only after activation/layout is working;
   verify the native vehicle and colored sectors actually appear and react.
5. If a separate video/compositor producer is required, identify that dependency
   from its calls and runtime behavior before proposing a replacement.

The separate `shark` webconfig `parkingTrigger` has not been established as an
HMI PDC trigger. It must not be treated as interchangeable with these interfaces.
Existing `didui/baureihePDC` vehicle assets alone also do not prove their rendering
path is active.

## Cleanup and evidence

The temporary probe was removed from the guest runtime, experimental coding was
reverted to the saved user overrides, and the HMI container was restarted with
the original native climate/music mock. The main project README, reboot
behavior, and public native mock implementation were not changed.

Private logs, screenshots, disassembly, coding snapshots, and probe source are
retained under `.local/pdc-investigation/`. They are research evidence, not
release assets; do not publish them or firmware as part of this document.
