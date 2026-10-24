// The ONE camera -> screen mapping. Everything that draws over the feed (the feed sprite itself,
// landmarks, effects, hit tests) goes through this, so overlays always sit on the bodies.
//
// Spaces:
//   cam    normalized camera image coords, un-mirrored, origin top-left (what trackers report)
//   view   normalized coords of the full camera frame AS SHOWN (mirrored when mirror = true)
//   screen CSS pixels of the canvas
//
// The feed is cover-fitted: scaled to fill the screen, centered, overflow cropped.

export function createViewTransform({ srcW, srcH, dstW, dstH, mirror = true }) {
  if (!(srcW > 0 && srcH > 0 && dstW > 0 && dstH > 0)) {
    throw new RangeError(`Invalid transform size: src ${srcW}x${srcH}, dst ${dstW}x${dstH}`);
  }
  const scale = Math.max(dstW / srcW, dstH / srcH);
  const drawnW = srcW * scale;
  const drawnH = srcH * scale;
  const offsetX = (dstW - drawnW) / 2; // <= 0: cropped amount on each side
  const offsetY = (dstH - drawnH) / 2;

  const camToView = (u, v) => ({ x: mirror ? 1 - u : u, y: v });
  const viewToCam = (x, y) => ({ u: mirror ? 1 - x : x, v: y });
  const viewToScreen = (x, y) => ({ x: offsetX + x * drawnW, y: offsetY + y * drawnH });
  const screenToView = (px, py) => ({ x: (px - offsetX) / drawnW, y: (py - offsetY) / drawnH });

  return {
    scale,
    drawnW,
    drawnH,
    offsetX,
    offsetY,
    mirror,
    camToView,
    viewToCam,
    viewToScreen,
    screenToView,
    camToScreen: (u, v) => {
      const view = camToView(u, v);
      return viewToScreen(view.x, view.y);
    },
    screenToCam: (px, py) => {
      const view = screenToView(px, py);
      return viewToCam(view.x, view.y);
    },
    // Placement for a sprite whose texture is the raw (un-mirrored) camera frame, anchor (0, 0).
    feedPlacement: () => ({
      x: mirror ? offsetX + drawnW : offsetX,
      y: offsetY,
      scaleX: mirror ? -scale : scale,
      scaleY: scale,
    }),
    // Screen length (px) of a distance expressed as a fraction of the shown frame height.
    viewLength: (fractionOfHeight) => fractionOfHeight * drawnH,
  };
}
