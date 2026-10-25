"""Game engine facade: Actions in, GameView and GameEvents out (spec section 8, game/).

Owner: Adetola
"""

import re
from collections.abc import Mapping, Sequence

from magic_box.core.config import Config
from magic_box.core.contracts import (
    Action,
    GameEvent,
    GameView,
    PlayerState,
    PlayerView,
    ProjectileView,
    SpellView,
    VoiceEvent,
)
from magic_box.game.combat import damage
from magic_box.game.scenes import SceneMachine
from magic_box.game.spells import spell_map
from magic_box.game.state import ChargeState, MatchState, ProjectileState


class Engine:
    """Pure rules engine. It owns mutable state but performs no I/O."""

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.state = MatchState(cfg)
        self.scenes = SceneMachine(cfg)
        self._incantations: dict[int, dict[str, str]] = {}
        self._chronicle: str | None = None
        self._events: list[GameEvent] = []
        self._last_scene = "boot"

    @property
    def event_log(self) -> tuple[GameEvent, ...]:
        return tuple(self._events)

    @property
    def classes(self) -> dict[int, str]:
        return {player.slot: player.class_id for player in self.state.players}

    @property
    def names(self) -> dict[int, str]:
        return {player.slot: player.name for player in self.state.players}

    def step(
        self, actions: Sequence[Action], states: Mapping[int, PlayerState], now: float
    ) -> tuple[GameView, list[GameEvent]]:
        emitted: list[GameEvent] = []
        scene = self.scenes.update(actions, states, now)
        if scene == "fight" and self._last_scene != "fight":
            self.state.reset(now)
            self._chronicle = None
            self._events = []
            emitted.append(self._event(now, "match_start", None, {}))
        self._last_scene = scene
        self._update_tracking(states)
        if scene == "fight" and not self.state.ended:
            self._advance(now, emitted)
            for action in sorted(actions, key=lambda item: item.t):
                self._apply(action, now, emitted)
            self._resolve_projectiles(now, emitted)
            self._finish_if_needed(now, emitted)
        if self.state.ended and self.scenes.scene == "fight":
            self.scenes.enter("victory", now)
            scene = "victory"
        self._events.extend(emitted)
        return self._view(scene, states, now), emitted

    def accept_voice(self, events: Sequence[VoiceEvent]) -> None:
        """Apply attributed lobby transcripts without adding new cross-process contracts."""
        if self.scenes.scene not in {"boot", "lobby"}:
            return
        for event in events:
            if event.kind == "transcript":
                self._apply_lobby_transcript(event)

    def provide_incantations(self, incantations: dict[int, dict[str, str]]) -> None:
        self._incantations = incantations
        self.scenes.complete_loading()

    def _apply_lobby_transcript(self, event: VoiceEvent) -> None:
        player = self.state.players[event.slot]
        text = " ".join(event.text.split())
        if not text:
            return
        player.mic_ok = True
        lobby = self.cfg["game"]["lobby"]
        for prefix in lobby["name_prefixes"]:
            match = re.fullmatch(rf"{re.escape(str(prefix))}\s+(.+?)[.!?]*", text, re.IGNORECASE)
            if match is None:
                continue
            words = match.group(1).split()[: int(lobby["name_max_words"])]
            name = " ".join(words)[: int(lobby["name_max_chars"])].strip(" ,.!?;:")
            if name:
                player.name = name.title()
            return

        normalized = re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()
        for class_id, row in self.cfg["game"]["classes"].items():
            choices = (str(class_id).replace("_", " "), str(row["name"]).lower())
            if any(normalized == choice or normalized.endswith(f" {choice}") for choice in choices):
                player.class_id = str(class_id)
                player.spells = spell_map(self.cfg, player.class_id)
                self._incantations.pop(event.slot, None)
                return

    def provide_chronicle(self, text: str) -> None:
        self._chronicle = text

    def _event(self, now: float, kind: str, slot: int | None, data: dict) -> GameEvent:
        return GameEvent(t=now, kind=kind, slot=slot, data=data)

    def _update_tracking(self, states: Mapping[int, PlayerState]) -> None:
        for player in self.state.players:
            state = states.get(player.slot)
            player.tracking_ok = bool(state and state.tracking_ok)
            if state is not None:
                player.zone = state.zone
                player.dist = state.root[2]

    def _advance(self, now: float, emitted: list[GameEvent]) -> None:
        previous = self.state.last_step_at
        self.state.last_step_at = now
        if previous is None:
            return
        dt = max(0.0, now - previous)
        tracked = all(player.tracking_ok for player in self.state.players)
        if tracked:
            self.state.tracking_lost_at = None
        elif self.state.tracking_lost_at is None:
            self.state.tracking_lost_at = now
        paused = (
            self.state.tracking_lost_at is not None
            and now - self.state.tracking_lost_at >= float(self.cfg["game"]["tracking_pause_s"])
        )
        if not paused:
            self.state.remaining_s = max(0.0, self.state.remaining_s - dt)
        game = self.cfg["game"]
        for player in self.state.players:
            regen = float(game["mana_regen_per_s"])
            if now < player.regen_slow_until:
                regen *= float(game["static_field_regen_mult"])
            player.mana = min(float(game["mana_max"]), player.mana + regen * dt)
            if player.charge is not None and now > player.charge.expires_at:
                spell = player.spells[player.charge.spell_id]
                player.mana = min(float(game["mana_max"]), player.mana + spell.cost)
                player.charge = None

    def _apply(self, action: Action, now: float, emitted: list[GameEvent]) -> None:
        player = self.state.players[action.slot]
        if action.kind == "charge" and action.spell_id is not None:
            spell = player.spells.get(action.spell_id)
            if spell is None or player.charge is not None or player.mana < spell.cost:
                return
            player.mana -= spell.cost
            player.charge = ChargeState(
                spell.id,
                now + float(self.cfg["game"]["charge_window_s"]),
                action.match_score,
            )
            return
        if action.kind == "dodge":
            player.last_dodge_at = action.t
            emitted.append(self._event(now, "dodge", action.slot, {"kind": action.dodge}))
            return
        if action.kind == "push" and action.push is not None:
            charge = player.charge
            if charge is not None:
                spell = player.spells[charge.spell_id]
                if spell.release == "push" or (
                    spell.release == "two_hand_push" and action.pose == "two_hand_push"
                ):
                    self._release(player.slot, spell.id, action, charge.match_score, emitted)
                return
            if now < player.basic_ready_at:
                return
            player.basic_ready_at = now + float(self.cfg["game"]["basic_attack_cooldown_s"])
            self._launch(
                action,
                "basic_attack",
                float(self.cfg["game"]["basic_attack_damage"]),
                float(self.cfg["game"]["basic_attack_travel_s"]),
                1.0,
                emitted,
            )
            return
        if action.kind == "pose" and player.charge is not None:
            spell = player.spells[player.charge.spell_id]
            required = {"arm_overhead": "hands_up", "hands_together": "hands_together"}.get(
                spell.release, spell.release
            )
            if action.pose == required:
                self._release(player.slot, spell.id, action, player.charge.match_score, emitted)

    def _release(
        self, slot: int, spell_id: str, action: Action, match_score: float, emitted: list[GameEvent]
    ) -> None:
        player = self.state.players[slot]
        spell = player.spells[spell_id]
        player.charge = None
        perfect = match_score >= float(self.cfg["voice"]["perfect_threshold"])
        cast_mult = float(self.cfg["game"]["perfect_incantation_mult"]) if perfect else 1.0
        if spell.id == "heal":
            player.hp = min(
                float(self.cfg["game"]["hp_max"]),
                player.hp + float(self.cfg["game"]["heal_amount"]),
            )
            emitted.append(self._event(action.t, "heal", slot, {"spell_id": spell.id}))
        elif spell.id == "holy_light":
            player.damage_buff_until = action.t + float(self.cfg["game"]["holy_light_s"])
            emitted.append(self._event(action.t, "buff", slot, {"spell_id": spell.id}))
        elif spell.id == "flame_wall":
            player.shield_until = action.t + float(self.cfg["game"]["flame_wall_s"])
            emitted.append(self._event(action.t, "buff", slot, {"spell_id": spell.id}))
        else:
            self._launch(action, spell.id, spell.damage, spell.travel_s, cast_mult, emitted)

    def _launch(
        self,
        action: Action,
        spell_id: str,
        base_damage: float,
        travel_s: float,
        cast_mult: float,
        emitted: list[GameEvent],
    ) -> None:
        player = self.state.players[action.slot]
        speed = (
            action.push.speed
            if action.push is not None
            else float(self.cfg["game"]["speed_reference_mps"])
        )
        origin = action.push.origin_px if action.push is not None else (0.0, 0.0)
        buff = (
            float(self.cfg["game"]["holy_light_mult"])
            if action.t < player.damage_buff_until
            else 1.0
        )
        projectile = ProjectileState(
            spell_id=spell_id,
            source_slot=action.slot,
            target_slot=1 - action.slot,
            origin_px=origin,
            launched_at=action.t,
            impacts_at=action.t + max(0.0, travel_s),
            base_damage=base_damage,
            push_speed=speed,
            attacker_dist=action.dist or player.dist,
            buff_mult=buff * cast_mult,
        )
        self.state.projectiles.append(projectile)
        emitted.append(
            self._event(
                action.t, "cast", action.slot, {"spell_id": spell_id, "target": 1 - action.slot}
            )
        )

    def _resolve_projectiles(self, now: float, emitted: list[GameEvent]) -> None:
        remaining: list[ProjectileState] = []
        for projectile in self.state.projectiles:
            if now < projectile.impacts_at:
                remaining.append(projectile)
                continue
            target = self.state.players[projectile.target_slot]
            dodge_start = projectile.impacts_at - float(self.cfg["game"]["dodge_window_s"])
            if dodge_start <= target.last_dodge_at <= projectile.impacts_at:
                continue
            if projectile.spell_id == "static_field":
                target.regen_slow_until = now + float(self.cfg["game"]["static_field_s"])
                emitted.append(
                    self._event(now, "buff", projectile.target_slot, {"spell_id": "static_field"})
                )
                continue
            amount = damage(
                projectile.base_damage,
                projectile.push_speed,
                projectile.attacker_dist,
                target.dist,
                projectile.buff_mult,
                self.cfg,
            )
            if projectile.spell_id == "chain":
                amount *= int(self.cfg["game"]["chain_hits"])
            if now <= target.shield_until:
                target.shield_until = 0.0
                emitted.append(
                    self._event(
                        now, "block", projectile.target_slot, {"spell_id": projectile.spell_id}
                    )
                )
                continue
            target.hp = max(0.0, target.hp - amount)
            emitted.append(
                self._event(
                    now,
                    "hit",
                    projectile.target_slot,
                    {
                        "spell_id": projectile.spell_id,
                        "damage": amount,
                        "from": projectile.source_slot,
                    },
                )
            )
            if target.hp <= 0 and not self.state.ended:
                self.state.ended = True
                self.state.winner = projectile.source_slot
                emitted.append(
                    self._event(now, "ko", target.slot, {"winner": projectile.source_slot})
                )
        self.state.projectiles = remaining

    def _finish_if_needed(self, now: float, emitted: list[GameEvent]) -> None:
        if self.state.ended or self.state.remaining_s > 0:
            if self.state.ended and not any(event.kind == "match_end" for event in emitted):
                emitted.append(self._event(now, "match_end", self.state.winner, {}))
            return
        hp = [player.hp for player in self.state.players]
        self.state.winner = None if hp[0] == hp[1] else (0 if hp[0] > hp[1] else 1)
        self.state.ended = True
        emitted.append(self._event(now, "match_end", self.state.winner, {"hp": hp}))

    def _view(self, scene: str, states: Mapping[int, PlayerState], now: float) -> GameView:
        players = tuple(self._player_view(slot, states.get(slot)) for slot in (0, 1))
        projectiles = tuple(self._projectile_view(item, now) for item in self.state.projectiles)
        banner = None
        if scene == "lobby":
            banner = "RAISE HANDS TO BEGIN"
        elif scene == "loading":
            banner = "PREPARING INCANTATIONS"
        elif scene == "fight" and any(not player.tracking_ok for player in self.state.players):
            banner = "STEP INTO VIEW"
        elif scene == "victory":
            banner = "DRAW" if self.state.winner is None else f"P{self.state.winner + 1} WINS"
        return GameView(
            scene=scene,
            players=players,
            projectiles=projectiles,
            banner=banner,
            timer_s=self.state.remaining_s if scene == "fight" else None,
            chronicle=self._chronicle if scene == "victory" else None,
        )

    def _player_view(self, slot: int, state: PlayerState | None) -> PlayerView:
        game = self.cfg["game"]
        player = self.state.players[slot]
        class_row = game["classes"][player.class_id]
        rows = {row["id"]: row for row in class_row["spells"]}
        spells = tuple(
            SpellView(
                id=spell.id,
                name=spell.name,
                incantation=self._incantations.get(slot, {}).get(
                    spell.id, str(rows[spell.id]["fallback"][slot])
                ),
                cost=spell.cost,
                charged=player.charge is not None and player.charge.spell_id == spell.id,
            )
            for spell in player.spells.values()
        )
        return PlayerView(
            slot=slot,
            name=player.name,
            class_id=player.class_id,
            hp=player.hp,
            hp_max=float(game["hp_max"]),
            mana=player.mana,
            mana_max=float(game["mana_max"]),
            spells=spells,
            zone=state.zone if state else player.zone,
            dist=state.root[2] if state else player.dist,
            mic_ok=player.mic_ok,
            tracking_ok=bool(state and state.tracking_ok),
        )

    def _projectile_view(self, projectile: ProjectileState, now: float) -> ProjectileView:
        duration = max(projectile.impacts_at - projectile.launched_at, 1e-9)
        progress = max(0.0, min(1.0, (now - projectile.launched_at) / duration))
        return ProjectileView(
            spell_id=projectile.spell_id,
            target_slot=projectile.target_slot,
            origin_px=projectile.origin_px,
            progress=progress,
            in_dodge_window=projectile.impacts_at - now
            <= float(self.cfg["game"]["dodge_window_s"]),
        )
