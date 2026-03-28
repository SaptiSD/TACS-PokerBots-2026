'''
madhav_claudeide_bot: Four-Phase Redraw Framework
Implements STRATEGY.md — tight-aggressive baseline with Phase 2 edge exploitation.
'''
import os
import sys
import random
from collections import Counter
from itertools import combinations

sys.path.append(os.path.join(os.path.dirname(__file__)))

from skeleton.actions import FoldAction, CallAction, CheckAction, RaiseAction, RedrawAction
from skeleton.bot import Bot
from skeleton.runner import parse_args, run_bot
from skeleton.states import STARTING_STACK, BIG_BLIND, SMALL_BLIND

# ---------------------------------------------------------------------------
# Card utilities
# ---------------------------------------------------------------------------

RANKS = '23456789TJQKA'
SUITS = 'cdhs'
FULL_DECK = [r + s for r in RANKS for s in SUITS]


def rank_val(c):
    return RANKS.index(c[0]) if c and len(c) >= 2 and c[0] in RANKS else -1


def suit_of(c):
    return c[1] if c and len(c) >= 2 else ''


def is_known(c):
    return bool(c) and c != '??'


# ---------------------------------------------------------------------------
# 7-card hand evaluator (string cards, no external dependencies)
# ---------------------------------------------------------------------------

def _score_5(cards):
    '''Score a 5-card hand. Returns comparable tuple (higher = better).'''
    ranks = sorted([rank_val(c) for c in cards], reverse=True)
    suits = [suit_of(c) for c in cards]
    rc = Counter(ranks)
    counts = sorted(rc.values(), reverse=True)
    is_flush = len(set(suits)) == 1
    is_straight = len(set(ranks)) == 5 and ranks[0] - ranks[4] == 4
    # Wheel: A-2-3-4-5 (ace plays low)
    if set(ranks) == {12, 3, 2, 1, 0}:
        is_straight = True
        ranks = [3, 2, 1, 0, -1]

    if is_straight and is_flush:
        return (8, ranks)
    if counts[0] == 4:
        q = max(r for r, n in rc.items() if n == 4)
        k = max(r for r, n in rc.items() if n == 1)
        return (7, [q, k])
    if counts[0] == 3 and counts[1] == 2:
        t = max(r for r, n in rc.items() if n == 3)
        p = max(r for r, n in rc.items() if n == 2)
        return (6, [t, p])
    if is_flush:
        return (5, ranks)
    if is_straight:
        return (4, ranks)
    if counts[0] == 3:
        t = max(r for r, n in rc.items() if n == 3)
        ks = sorted([r for r, n in rc.items() if n == 1], reverse=True)
        return (3, [t] + ks)
    if counts == [2, 2, 1]:
        ps = sorted([r for r, n in rc.items() if n == 2], reverse=True)
        k = max(r for r, n in rc.items() if n == 1)
        return (2, ps + [k])
    if counts[0] == 2:
        p = max(r for r, n in rc.items() if n == 2)
        ks = sorted([r for r, n in rc.items() if n == 1], reverse=True)
        return (1, [p] + ks)
    return (0, ranks)


def evaluate_hand(cards):
    '''Best 5-card hand from 5-7 cards. Returns comparable tuple (higher = better).'''
    valid = [c for c in cards if is_known(c)]
    if len(valid) < 5:
        return (0, [rank_val(c) for c in valid])
    best = None
    for combo in combinations(valid, 5):
        s = _score_5(list(combo))
        if best is None or s > best:
            best = s
    return best


# ---------------------------------------------------------------------------
# Monte Carlo equity estimation
# ---------------------------------------------------------------------------

def _remaining_deck(hole, board, dead_extra=None):
    dead = set(c for c in hole if is_known(c))
    dead |= set(c for c in board if is_known(c))
    if dead_extra:
        dead |= set(c for c in dead_extra if is_known(c))
    return [c for c in FULL_DECK if c not in dead]


def estimate_equity(hole, board, dead_extra=None, n_samples=120):
    '''
    Win probability for hole+board vs random opponent via Monte Carlo.
    dead_extra: additional known-dead cards (e.g. opponent's discard).
    '''
    remaining = _remaining_deck(hole, board, dead_extra)
    board_needed = 5 - len(board)
    wins = 0.0
    valid = 0
    need = board_needed + 2  # remaining board + opp 2 hole cards

    for _ in range(n_samples):
        if len(remaining) < need:
            break
        sample = random.sample(remaining, need)
        full_board = list(board) + sample[:board_needed]
        opp_hand = sample[board_needed:]
        my_s = evaluate_hand(list(hole) + full_board)
        op_s = evaluate_hand(opp_hand + full_board)
        if my_s > op_s:
            wins += 1.0
        elif my_s == op_s:
            wins += 0.5
        valid += 1

    return wins / valid if valid > 0 else 0.5


def estimate_equity_with_redraw(hole, board, target_type, target_index,
                                dead_extra=None, n_samples=120):
    '''
    Expected equity after redrawing the given target (samples replacement inline).
    Each sample draws: replacement card + remaining board + opponent hand together.
    '''
    remaining = _remaining_deck(hole, board, dead_extra)
    board_needed = 5 - len(board)
    wins = 0.0
    valid = 0
    need = 1 + board_needed + 2  # replacement + board completion + opp hand

    for _ in range(n_samples):
        if len(remaining) < need:
            break
        sample = random.sample(remaining, need)
        replacement = sample[0]
        full_board = list(board) + sample[1:1 + board_needed]
        opp_hand = sample[1 + board_needed:]

        if target_type == 'hole':
            new_hole = list(hole)
            new_hole[target_index] = replacement
            eval_board = full_board
        else:
            new_hole = list(hole)
            eval_board = list(full_board)
            eval_board[target_index] = replacement  # replace already-dealt board card

        my_s = evaluate_hand(new_hole + eval_board)
        op_s = evaluate_hand(opp_hand + eval_board)
        if my_s > op_s:
            wins += 1.0
        elif my_s == op_s:
            wins += 0.5
        valid += 1

    return wins / valid if valid > 0 else 0.5


# ---------------------------------------------------------------------------
# Preflop hand strength
# ---------------------------------------------------------------------------

def preflop_score(hole):
    '''Returns a 0-1 strength score for our two hole cards.'''
    if len(hole) < 2 or not all(is_known(c) for c in hole):
        return 0.5
    r0, r1 = rank_val(hole[0]), rank_val(hole[1])
    s0, s1 = suit_of(hole[0]), suit_of(hole[1])
    hi, lo = max(r0, r1), min(r0, r1)
    suited = s0 == s1
    is_pair = r0 == r1
    gap = hi - lo

    if is_pair:
        # AA = 0.98, KK = 0.96, ... 22 = 0.72
        return 0.72 + hi * 0.02

    # Non-paired
    base = (hi + lo) / 26.0  # 0..1 range approx
    score = base
    if suited:
        score += 0.06
    if gap == 1:
        score += 0.04   # connector
    elif gap == 2:
        score += 0.02   # one-gapper
    if hi == 12:
        score += 0.05   # ace bonus
    if hi >= 11 and lo >= 9:
        score += 0.03   # broadways

    return min(score, 1.0)


# ---------------------------------------------------------------------------
# Postflop hand bucketing
# ---------------------------------------------------------------------------

def bucket_postflop(hole, board):
    '''
    Returns 'strong', 'medium', 'weak', or 'air'.
    Uses hand category and board texture.
    '''
    valid_hole = [c for c in hole if is_known(c)]
    valid_board = [c for c in board if is_known(c)]
    if len(valid_hole) < 1 or len(valid_board) < 3:
        return 'air'

    score = evaluate_hand(valid_hole + valid_board)
    hand_type = score[0]

    if hand_type >= 4:          # straight or better
        return 'strong'
    if hand_type == 3:          # three of a kind
        return 'strong'
    if hand_type == 2:          # two pair
        board_ranks = sorted([rank_val(c) for c in valid_board], reverse=True)
        pair_ranks = score[1][:2] if len(score[1]) >= 2 else score[1]
        if max(pair_ranks) >= board_ranks[0]:
            return 'strong'
        return 'medium'
    if hand_type == 1:          # one pair
        board_ranks = sorted([rank_val(c) for c in valid_board], reverse=True)
        pair_rank = score[1][0]
        if pair_rank >= board_ranks[0]:                 # top pair
            kicker = score[1][1] if len(score[1]) > 1 else 0
            return 'strong' if kicker >= 7 else 'medium'
        if len(board_ranks) > 1 and pair_rank >= board_ranks[1]:
            return 'medium'
        return 'weak'

    # No pair — check draws
    all_cards = valid_hole + valid_board
    all_suits = [suit_of(c) for c in all_cards]
    for s in SUITS:
        if all_suits.count(s) >= 4:
            return 'medium'     # flush draw

    all_ranks = sorted(set(rank_val(c) for c in all_cards if rank_val(c) >= 0))
    for i in range(len(all_ranks) - 3):
        span = all_ranks[i + 3] - all_ranks[i]
        if span <= 4:
            return 'medium'     # open-ended straight draw / gutshot

    hi_hole = max((rank_val(c) for c in valid_hole), default=-1)
    return 'weak' if hi_hole >= 9 else 'air'


# ---------------------------------------------------------------------------
# Opponent model
# ---------------------------------------------------------------------------

class OppModel:
    def __init__(self):
        self.hands_seen = 0
        self.redraws = 0
        self.hole_redraws = 0
        self.board_redraws = 0

    def record_redraw(self, redraw_type):
        self.redraws += 1
        if redraw_type == 'hole':
            self.hole_redraws += 1
        else:
            self.board_redraws += 1

    @property
    def redraw_freq(self):
        if self.hands_seen == 0:
            return 0.2
        return self.redraws / self.hands_seen

    @property
    def prefers_board_redraws(self):
        return self.board_redraws > self.hole_redraws if self.redraws >= 5 else False


# ---------------------------------------------------------------------------
# Main bot
# ---------------------------------------------------------------------------

class Player(Bot):
    def __init__(self):
        self.opp_model = OppModel()
        # Per-hand state (reset in handle_new_round)
        self._active = 0
        self._we_redrawn = False
        self._opp_redrawn = False
        self._opp_redraw_type = None    # 'hole' or 'board'
        self._opp_discard = None        # card string revealed by engine

    # ------------------------------------------------------------------
    # Lifecycle hooks
    # ------------------------------------------------------------------

    def handle_new_round(self, game_state, round_state, active):
        self._active = active
        self._we_redrawn = False
        self._opp_redrawn = False
        self._opp_redraw_type = None
        self._opp_discard = None
        self.opp_model.hands_seen += 1

    def handle_round_over(self, game_state, terminal_state, active):
        pass

    def on_opponent_redraw(self, target_type, target_index, old_card):
        '''Called by runner when opponent redraws. Records discard for Monte Carlo.'''
        if not self._opp_redrawn:
            self._opp_redrawn = True
            self._opp_redraw_type = target_type
            self._opp_discard = old_card
            self.opp_model.record_redraw(target_type)

    # ------------------------------------------------------------------
    # Phase detection
    # ------------------------------------------------------------------

    def _sync_state(self, round_state):
        '''Sync redrawn flags from round_state in case on_opponent_redraw wasn't called.'''
        opp = 1 - self._active
        if round_state.redraws_used[self._active]:
            self._we_redrawn = True
        if round_state.redraws_used[opp] and not self._opp_redrawn:
            self._opp_redrawn = True
            # Detect type: board has '??' → board redraw; otherwise hole redraw
            if any(c == '??' for c in round_state.board):
                self._opp_redraw_type = 'board'
            else:
                self._opp_redraw_type = 'hole'
            self.opp_model.record_redraw(self._opp_redraw_type)

    def _phase(self):
        if not self._we_redrawn and not self._opp_redrawn:
            return 1
        if not self._we_redrawn and self._opp_redrawn:
            return 2
        if self._we_redrawn and not self._opp_redrawn:
            return 3
        return 4  # both redrawn

    # ------------------------------------------------------------------
    # Redraw decision engine
    # ------------------------------------------------------------------

    def _redraw_threshold(self, phase):
        if phase == 1:
            return 0.12
        if phase == 2:
            return 0.05 if self._opp_redraw_type == 'board' else 0.08
        return 0.99  # phases 3/4: redraw already used

    def _best_redraw(self, hole, board, phase, n_samples=120):
        '''
        Evaluate all redraw targets. Returns (target_type, target_index, equity_gain)
        or (None, None, 0) if no candidate exceeds the threshold.
        '''
        dead_extra = [self._opp_discard] if self._opp_discard else []
        current_eq = estimate_equity(hole, board, dead_extra=dead_extra, n_samples=n_samples)
        threshold = self._redraw_threshold(phase)

        best_type, best_idx, best_eq = None, None, current_eq

        # Hole card candidates
        for hi in range(2):
            if not is_known(hole[hi]):
                continue
            eq = estimate_equity_with_redraw(hole, board, 'hole', hi,
                                             dead_extra=dead_extra, n_samples=n_samples)
            if eq > best_eq:
                best_eq, best_type, best_idx = eq, 'hole', hi

        # Board card candidates (phase 1: higher implicit cost, phase 2 after board redraw: lower)
        # We apply an extra penalty to board redraws in phase 1 to account for volatility.
        board_threshold_mult = 1.5 if phase == 1 else 1.0
        for bi in range(len(board)):
            if not is_known(board[bi]):
                continue
            eq = estimate_equity_with_redraw(hole, board, 'board', bi,
                                             dead_extra=dead_extra, n_samples=n_samples)
            gain = eq - current_eq
            if gain > threshold * board_threshold_mult and eq > best_eq:
                best_eq, best_type, best_idx = eq, 'board', bi

        gain = best_eq - current_eq
        if best_type is not None and gain > threshold:
            return best_type, best_idx, gain
        return None, None, 0.0

    # ------------------------------------------------------------------
    # Betting action helpers
    # ------------------------------------------------------------------

    def _pot_size(self, round_state):
        return 2 * STARTING_STACK - round_state.stacks[0] - round_state.stacks[1]

    def _raise_to(self, round_state, pot_fraction):
        '''Build a RaiseAction sized to pot_fraction of the pot. Clamps to legal bounds.'''
        legal = round_state.legal_actions()
        if RaiseAction not in legal:
            return None
        mn, mx = round_state.raise_bounds()
        pot = self._pot_size(round_state)
        pip = round_state.pips[self._active]
        target = int(pip + pot_fraction * (pot + pip))
        amount = max(mn, min(mx, target))
        return RaiseAction(amount)

    def _betting_action(self, round_state, strength, phase):
        '''Return best betting action given hand strength and current phase.'''
        active = self._active
        legal = round_state.legal_actions()
        my_pip = round_state.pips[active]
        opp_pip = round_state.pips[1 - active]
        continue_cost = opp_pip - my_pip
        pot = self._pot_size(round_state)

        # Phase 2: increase aggression since opponent is weakened
        agg = 1.3 if phase == 2 else (0.85 if phase == 3 else 1.0)

        if strength == 'strong':
            r = self._raise_to(round_state, 0.65 * agg)
            if r:
                return r
            if CallAction in legal:
                return CallAction()
            return CheckAction()

        if strength == 'medium':
            r = self._raise_to(round_state, 0.40 * agg)
            if r and continue_cost == 0:
                return r
            if CallAction in legal:
                max_call = max(pot * 0.45, BIG_BLIND * 3)
                if continue_cost <= max_call:
                    return CallAction()
                return FoldAction()
            return CheckAction()

        if strength == 'weak':
            if CheckAction in legal:
                return CheckAction()
            if CallAction in legal and continue_cost <= BIG_BLIND * 2:
                return CallAction()
            return FoldAction()

        # Air
        if CheckAction in legal:
            # Occasional bluff in Phase 2 (opponent hand is partially random)
            if phase == 2 and random.random() < 0.22:
                r = self._raise_to(round_state, 0.5)
                if r:
                    return r
            return CheckAction()
        return FoldAction()

    # ------------------------------------------------------------------
    # Preflop logic
    # ------------------------------------------------------------------

    def _preflop_action(self, round_state):
        active = self._active
        legal = round_state.legal_actions()
        hole = round_state.hands[active]
        pf = preflop_score(hole)
        my_pip = round_state.pips[active]
        opp_pip = round_state.pips[1 - active]
        continue_cost = opp_pip - my_pip

        if active == 0:
            # SB / Button — acts first preflop
            if pf >= 0.55:
                # Open raise to ~2.5x BB
                r = self._raise_to(round_state, 0)
                if RaiseAction in legal:
                    mn, mx = round_state.raise_bounds()
                    amount = max(mn, min(mx, int(2.5 * BIG_BLIND)))
                    return RaiseAction(amount)
                if CallAction in legal:
                    return CallAction()
                return CheckAction()
            return FoldAction() if FoldAction in legal else CheckAction()

        else:
            # BB — acts last preflop
            if continue_cost == 0:
                # Nobody raised; we can check or raise
                if pf >= 0.65 and RaiseAction in legal:
                    mn, mx = round_state.raise_bounds()
                    amount = max(mn, min(mx, int(3 * BIG_BLIND)))
                    return RaiseAction(amount)
                return CheckAction() if CheckAction in legal else CallAction()
            else:
                # Facing a raise
                if pf >= 0.80 and RaiseAction in legal:
                    # 3-bet
                    mn, mx = round_state.raise_bounds()
                    amount = max(mn, min(mx, int(3 * continue_cost + my_pip)))
                    return RaiseAction(amount)
                if pf >= 0.52 and CallAction in legal:
                    return CallAction()
                return FoldAction()

    # ------------------------------------------------------------------
    # Main action dispatcher
    # ------------------------------------------------------------------

    def get_action(self, game_state, round_state, active):
        self._active = active
        self._sync_state(round_state)

        legal = round_state.legal_actions()
        hole = round_state.hands[active]
        board = round_state.board
        street = round_state.street
        phase = self._phase()

        # Preflop: no redraws possible, pure standard play
        if street == 0:
            return self._preflop_action(round_state)

        # Postflop
        strength = bucket_postflop(hole, board)

        # Evaluate redraw if still available and on flop/turn
        if RedrawAction in legal and street in (3, 4) and not self._we_redrawn:
            rt, ri, gain = self._best_redraw(hole, board, phase)
            if rt is not None:
                self._we_redrawn = True
                betting = self._betting_action(round_state, strength, phase)
                return RedrawAction(rt, ri, betting)

        return self._betting_action(round_state, strength, phase)


if __name__ == '__main__':
    run_bot(Player(), parse_args())
