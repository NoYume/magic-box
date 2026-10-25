# Sword vs mage — spatial concept study

Owner: Adetola

A standalone Three.js animation. It does not modify the playable Arena or implement combat/gesture detection.

## Open

From the repository root:

```sh
uv run python -m http.server 5174 --bind 127.0.0.1 --directory game
```

Visit http://localhost:5174/sword-demo.html. Alternatively use the existing game development server and open `/sword-demo.html`.

Internet access is required for Three.js (pinned CDN imports) and optional Google fonts. A WebGL-capable browser is required.

## Controls

- Play / pause (or Space outside a form control).
- Scrub the timeline or select Ready / Cast / Parry / Riposte.
- Room / Overhead / Player eye camera presets.
- Drag the room to orbit; scroll to zoom.
- Reduced-motion preference starts the demo paused.

## What this proposes

Both players face one monitor/camera. P1 stands on their own left and watches the mage on the left display half; P2 watches the knight on the right. Front-camera crops are deliberately unmirrored; each half shows the opponent, not the viewer.

1. The mage speaks and pushes toward the camera. A virtual spell approaches P1's viewpoint.
2. The knight raises a forward guard. A successful timed parry flashes a first-person shield and earns a riposte.
3. The knight thrusts an empty hand forward. A virtual blade wave approaches P2's viewpoint.
4. The mage steps sideways inside their own lane to dodge.

The monitor and the enlarged display preview use the **same canvas texture**, compositing live front-facing 3D crops and screen-only combat effects. The room never contains a real sword or a projectile moving between players.

This is a scripted illustration, not a balance simulation. Guard recognition, impact timing, safe lane spacing, and movement thresholds need validation with the perception/intent owners. Dimensions are illustrative, not a measured hardware installation. The front-facing crops approximate the eventual central camera's opponent crops.

Timeline checks: `node --test game/test/sword-demo-timeline.test.js`.
