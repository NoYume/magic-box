/** Scripted concept-study timing, not production combat rules. Owner: Adetola. */
export const BEATS = [
  { start: 0, duration: 2.5, label: 'Ready', title: 'Two lanes. One shared display.', description: 'Both players face the display and camera. P1 watches the mage on the left half; P2 watches the sword user on the right. Their physical bodies never turn toward each other.' },
  { start: 2.5, duration: 4, label: 'Cast', title: 'The mage pushes toward the camera.', description: 'The mage speaks an incantation, then extends a hand forward. A spell approaches P1’s viewpoint on the LEFT half. Nothing flies across the room: projectile direction is virtual, not a line between the players.' },
  { start: 6.5, duration: 2.5, label: 'Parry', title: 'Guard forward. Catch the timing.', description: 'The sword user raises their forearms in front of their chest, still looking at the display. Timing that pose with the incoming spell produces a first-person shield flash on P1’s half and earns one empowered riposte. This gesture is a proposal, not validated tracking.' },
  { start: 9, duration: 4.5, label: 'Riposte', title: 'Thrust forward. The mage steps aside.', description: 'P1 thrusts one empty hand toward the camera, launching a virtual blade wave toward P2’s viewpoint on the RIGHT half. The mage sidesteps inside their own lane and dodges. No real sword, lateral swing, or contact is needed.' },
];
export const DURATION = 13.5;
export function sample(time) {
  const t = Math.max(0, Math.min(DURATION - 0.00001, time));
  let index = BEATS.findIndex(b => t < b.start + b.duration);
  if (index < 0) index = BEATS.length - 1;
  return { index, progress: (t - BEATS[index].start) / BEATS[index].duration, t };
}
export function smooth(a, b, value) {
  const x = Math.max(0, Math.min(1, (value - a) / (b - a)));
  return x * x * (3 - 2 * x);
}
