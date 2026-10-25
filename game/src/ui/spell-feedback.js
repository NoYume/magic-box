// Short, high-contrast cast verdicts positioned over the player who spoke.

const ABILITY_NAMES = Object.freeze({
  bolt: 'Bolt',
  ward: 'Ward',
  gather: 'Gather',
  ultimate: 'Ultimate',
});

export class SpellFeedback {
  constructor(root) {
    this.root = document.createElement('div');
    this.root.className = 'spell-feedback';
    this.root.setAttribute('role', 'status');
    this.root.setAttribute('aria-live', 'assertive');
    this.root.setAttribute('aria-atomic', 'true');
    this.root.innerHTML = `
      <div class="spell-feedback__sigil" aria-hidden="true"><i></i></div>
      <div class="spell-feedback__copy">
        <span class="spell-feedback__kicker"></span>
        <strong></strong>
        <span class="spell-feedback__reason"></span>
      </div>`;
    root.append(this.root);
    this.kicker = this.root.querySelector('.spell-feedback__kicker');
    this.title = this.root.querySelector('strong');
    this.reason = this.root.querySelector('.spell-feedback__reason');
    this.timer = null;
  }

  show({ success, ability = null, reason, slot = null }) {
    clearTimeout(this.timer);
    this.root.classList.remove('is-visible');
    this.root.dataset.kind = success ? 'success' : 'failure';
    this.root.dataset.slot = slot ?? 'center';
    const player = slot === null ? 'Voice command' : `Player ${slot + 1}`;
    const spell = ABILITY_NAMES[ability] ?? 'Spell';
    this.kicker.textContent = `${player} / ${spell}`;
    this.title.textContent = success ? 'Spell successful' : 'Spell unsuccessful';
    this.reason.textContent = success ? `${spell} answered the call.` : reason;
    void this.root.offsetWidth; // replay the entrance for consecutive commands
    this.root.classList.add('is-visible');
    this.timer = setTimeout(() => this.root.classList.remove('is-visible'), success ? 1700 : 2600);
  }
}
