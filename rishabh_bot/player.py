'''
rishabh_bot — Build4Good 2026 PokerBot

Strategy: preflop lookup table (n=100k Monte Carlo) + on-the-fly MC postflop.
Opponent cannot redraw — our redraw is a pure asymmetric edge.

Rules:
  - 400 chips/hand, blinds 1 (SB) / 2 (BB), 300 hands/match
  - Streets: 0=preflop, 3=flop, 4=turn, 5=river
  - RedrawAction(target_type, target_index, betting_action)
    'hole' index 0-1  |  'board' index 0-2 (flop), 0-3 (turn)
'''

import os
import random
import pickle
from collections import Counter

from skeleton.actions import FoldAction, CallAction, CheckAction, RaiseAction, RedrawAction
from skeleton.states import STARTING_STACK, BIG_BLIND
from skeleton.bot import Bot
from skeleton.runner import parse_args, run_bot

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

RANKS = '23456789TJQKA'
SUITS = 'cdhs'
DECK  = [r + s for r in RANKS for s in SUITS]

_HERE       = os.path.dirname(os.path.abspath(__file__))
LOOKUP_PATH = os.path.join(_HERE, 'preflop_lookup.pkl')

# Redraw thresholds — lower bar since opponent cannot redraw
PREFLOP_REDRAW_EQ_MAX   = 0.44
PREFLOP_REDRAW_MIN_GAIN = 0.03
POST_REDRAW_EQ_MAX      = 0.42
POST_REDRAW_MIN_GAIN    = 0.04

# Betting thresholds
RAISE_STRONG   = 0.65
RAISE_MODERATE = 0.54
CALL_MIN       = 0.40
BLUFF_MAX      = 0.22
FOLD_VS_RAISE  = 0.36


# ---------------------------------------------------------------------------
# Preflop lookup table
# ---------------------------------------------------------------------------

def _load_lookup():
    try:
        with open(LOOKUP_PATH, 'rb') as f:
            return pickle.load(f)
    except FileNotFoundError:
        return {}

LOOKUP = _load_lookup()


def hand_to_key(cards):
    r0, s0 = cards[0][0], cards[0][1]
    r1, s1 = cards[1][0], cards[1][1]
    i0, i1 = RANKS.index(r0), RANKS.index(r1)
    if i0 < i1:
        r0, s0, i0, r1, s1, i1 = r1, s1, i1, r0, s0, i0
    if i0 == i1:
        return f"{r0}{r1}"
    return f"{r0}{r1}s" if s0 == s1 else f"{r0}{r1}o"


# ---------------------------------------------------------------------------
# Hand evaluator (pure Python, no external libs)
# ---------------------------------------------------------------------------

def _parse(card):
    return (RANKS.index(card[0]), SUITS.index(card[1]))


def _hand_rank(cards):
    ranks = [c[0] for c in cards]
    suits = [c[1] for c in cards]

    flush_suit = next((s for s in range(4) if suits.count(s) >= 5), None)
    fc = [c for c in cards if c[1] == flush_suit] if flush_suit is not None else []

    def best_str(rs):
        rs = sorted(rs)
        if 12 in rs:
            rs = [-1] + rs
        best = -1
        for i in range(len(rs) - 4):
            w = rs[i:i+5]
            if w[-1] - w[0] == 4 and len(set(w)) == 5:
                best = max(best, w[-1])
        return best

    if fc:
        sf = best_str({c[0] for c in fc})
        if sf >= 0:
            return (8, sf)

    cnt    = Counter(ranks)
    groups = sorted(cnt.items(), key=lambda x: (x[1], x[0]), reverse=True)
    counts = [g[1] for g in groups]
    ordered = []
    for r, c in groups:
        ordered.extend([r] * c)

    if counts[0] == 4:                            return (7, ordered)
    if counts[0] == 3 and counts[1] >= 2:         return (6, ordered)
    if fc:                                        return (5, sorted([c[0] for c in fc], reverse=True)[:5])
    sh = best_str(set(ranks))
    if sh >= 0:                                   return (4, [sh])
    if counts[0] == 3:                            return (3, ordered)
    if counts[0] == 2 and counts[1] == 2:         return (2, ordered)
    if counts[0] == 2:                            return (1, ordered)
    return (0, sorted(ranks, reverse=True))


_7C5 = [
    (0,1,2,3,4),(0,1,2,3,5),(0,1,2,3,6),(0,1,2,4,5),(0,1,2,4,6),
    (0,1,2,5,6),(0,1,3,4,5),(0,1,3,4,6),(0,1,3,5,6),(0,1,4,5,6),
    (0,2,3,4,5),(0,2,3,4,6),(0,2,3,5,6),(0,2,4,5,6),(0,3,4,5,6),
    (1,2,3,4,5),(1,2,3,4,6),(1,2,3,5,6),(1,2,4,5,6),(1,3,4,5,6),
    (2,3,4,5,6),
]


def best_hand(hole, board):
    all_cards = [c for c in hole + board if c and c != '??']
    parsed    = [_parse(c) for c in all_cards]
    n         = len(parsed)
    if n < 5:
        return (-1,)
    best = (-1,)
    for idx in (_7C5 if n == 7 else [tuple(range(n))]):
        if max(idx) < n:
            s = _hand_rank([parsed[i] for i in idx])
            if s > best:
                best = s
    return best


# ---------------------------------------------------------------------------
# Monte Carlo
# ---------------------------------------------------------------------------

def _pool(hole, board):
    known = {c for c in hole + board if c and c != '??'}
    return [c for c in DECK if c not in known]


def mc_equity(hole, board, n=200):
    pool = _pool(hole, board)
    bn   = 5 - len(board)
    wins = 0.0
    for _ in range(n):
        s  = random.sample(pool, bn + 2)
        fb = board + s[2:]
        my = best_hand(hole,  fb)
        op = best_hand(s[:2], fb)
        if   my > op: wins += 1.0
        elif my == op: wins += 0.5
    return wins / n


def mc_redraw_hole(hole, board, idx, n=120):
    pool = _pool(hole, board)
    bn   = 5 - len(board)
    wins = 0.0; cnt = 0
    for _ in range(n):
        if len(pool) < 1 + bn + 2: break
        s        = random.sample(pool, 1 + bn + 2)
        nh       = list(hole); nh[idx] = s[0]
        fb       = board + s[1:1+bn]
        my = best_hand(nh,      fb)
        op = best_hand(s[1+bn:], fb)
        if   my > op: wins += 1.0
        elif my == op: wins += 0.5
        cnt += 1
    return wins / cnt if cnt else 0.0


def mc_redraw_board(hole, board, bidx, n=120):
    pool = _pool(hole, board)
    bn   = 5 - len(board)
    wins = 0.0; cnt = 0
    for _ in range(n):
        if len(pool) < 1 + bn + 2: break
        s        = random.sample(pool, 1 + bn + 2)
        nb       = list(board); nb[bidx] = s[0]
        fb       = nb + s[1:1+bn]
        my = best_hand(hole,     fb)
        op = best_hand(s[1+bn:], fb)
        if   my > op: wins += 1.0
        elif my == op: wins += 0.5
        cnt += 1
    return wins / cnt if cnt else 0.0


def best_redraw_option(hole, board, n=100):
    """Returns (best_equity, target_type, target_index)."""
    best = (-1.0, 'hole', 0)
    for i in range(len(hole)):
        if not hole[i] or hole[i] == '??': continue
        eq = mc_redraw_hole(hole, board, i, n)
        if eq > best[0]: best = (eq, 'hole', i)
    for i in range(len(board)):
        if not board[i] or board[i] == '??': continue
        eq = mc_redraw_board(hole, board, i, n)
        if eq > best[0]: best = (eq, 'board', i)
    return best


# ---------------------------------------------------------------------------
# Betting
# ---------------------------------------------------------------------------

def choose_bet(equity, pot_odds, legal, min_r, max_r, cost, stack, rounds, opp_agg):
    bluff = 0.06 if rounds > 20 and opp_agg / (rounds + 1) < 0.25 else 0.02

    if RaiseAction in legal:
        if equity >= 0.80:
            return RaiseAction(max_r)
        if equity >= RAISE_STRONG:
            return RaiseAction(max(min_r, min(max_r, int(min_r * 1.6))))
        if equity >= RAISE_MODERATE:
            return RaiseAction(min_r)
        if equity < BLUFF_MAX and random.random() < bluff:
            return RaiseAction(min_r)

    # Call if equity beats our floor OR the pot is laying better odds than the floor.
    # For large bets (pot_odds > CALL_MIN), require equity to cover pot odds.
    call_thresh = pot_odds if pot_odds > CALL_MIN else CALL_MIN
    if equity >= call_thresh:
        if CallAction in legal and cost > 0:
            return CallAction()
        if CheckAction in legal:
            return CheckAction()

    if CheckAction in legal:
        return CheckAction()
    if FoldAction in legal:
        return FoldAction()
    return CallAction()


# ---------------------------------------------------------------------------
# Bot
# ---------------------------------------------------------------------------

class Player(Bot):

    def __init__(self):
        self.opp_agg      = 0
        self.rounds_played = 0

    def handle_new_round(self, game_state, round_state, active):
        pass

    def handle_round_over(self, game_state, terminal_state, active):
        prev = terminal_state.previous_state
        if prev.pips[1 - active] > BIG_BLIND * 2:
            self.opp_agg += 1
        self.rounds_played += 1

    def get_action(self, game_state, round_state, active):
        try:
            return self._get_action(game_state, round_state, active)
        except Exception:
            legal = round_state.legal_actions()
            return CheckAction() if CheckAction in legal else (FoldAction() if FoldAction in legal else CallAction())

    def _get_action(self, game_state, round_state, active):
        legal         = round_state.legal_actions()
        street        = round_state.street
        my_cards      = round_state.hands[active]
        board         = list(round_state.board)
        my_pip        = round_state.pips[active]
        opp_pip       = round_state.pips[1 - active]
        cost          = opp_pip - my_pip
        pot           = sum(round_state.pips) + cost
        my_stack      = round_state.stacks[active]

        min_r = max_r = None
        if RaiseAction in legal:
            min_r, max_r = round_state.raise_bounds()

        pot_odds   = cost / (pot + 1e-9)
        # Engine allows only ONE redraw per hand total. If opponent already redrawed, we can't.
        opp_redrawed = round_state.redraws_used[1 - active]
        can_redraw = RedrawAction in legal and not opp_redrawed

        # -------------------------------------------------------------------
        # Preflop
        # -------------------------------------------------------------------
        if street == 0:
            valid = [c for c in my_cards if c and c != '??']
            if len(valid) < 2:
                return CheckAction() if CheckAction in legal else FoldAction()

            key   = hand_to_key(valid)
            entry = LOOKUP.get(key)

            if entry:
                equity     = entry['equity']
                best_r_eq  = entry['best_redraw']
                gain       = entry['redraw_gain']
                best_r_idx = entry['best_redraw_card']
            else:
                # Table missing — quick fallback
                equity    = mc_equity(valid, [], n=400)
                r0        = mc_redraw_hole(valid, [], 0, n=150)
                r1        = mc_redraw_hole(valid, [], 1, n=150)
                best_r_eq = max(r0, r1)
                gain      = best_r_eq - equity
                best_r_idx = 0 if r0 >= r1 else 1

            # Fold weak hands facing a raise — use pot-odds threshold for large bets
            fold_thresh = max(FOLD_VS_RAISE, pot_odds * 0.85) if pot_odds > FOLD_VS_RAISE else FOLD_VS_RAISE
            if cost > BIG_BLIND and equity < fold_thresh:
                if FoldAction in legal:
                    return FoldAction()

            # Redraw preflop — only when we're raising or checking (not calling/folding).
            # Engine doesn't accept RedrawAction with CallAction inner bet.
            # No point redrawing if we'd fold anyway.
            if can_redraw and equity < PREFLOP_REDRAW_EQ_MAX and gain >= PREFLOP_REDRAW_MIN_GAIN:
                bet = choose_bet(best_r_eq, pot_odds, legal, min_r, max_r,
                                 cost, my_stack, self.rounds_played, self.opp_agg)
                if isinstance(bet, (RaiseAction, CheckAction)):
                    return RedrawAction('hole', best_r_idx, bet)

            return choose_bet(equity, pot_odds, legal, min_r, max_r,
                              cost, my_stack, self.rounds_played, self.opp_agg)

        # -------------------------------------------------------------------
        # Flop / Turn / River
        # -------------------------------------------------------------------
        iters  = {3: 200, 4: 260, 5: 340}.get(street, 200)
        equity = mc_equity(my_cards, board, n=iters)

        # Postflop redraw — only when we're raising or checking
        if can_redraw and equity < POST_REDRAW_EQ_MAX:
            best_r_eq, ttype, tidx = best_redraw_option(my_cards, board, n=iters // 3)
            if best_r_eq - equity >= POST_REDRAW_MIN_GAIN:
                bet = choose_bet(best_r_eq, pot_odds, legal, min_r, max_r,
                                 cost, my_stack, self.rounds_played, self.opp_agg)
                if isinstance(bet, (RaiseAction, CheckAction)):
                    return RedrawAction(ttype, tidx, bet)

        # With shallow stack-to-pot, commit with decent equity
        spr = my_stack / (pot + 1e-9)
        if spr < 3 and equity >= 0.52 and RaiseAction in legal:
            return RaiseAction(max_r)

        return choose_bet(equity, pot_odds, legal, min_r, max_r,
                          cost, my_stack, self.rounds_played, self.opp_agg)


if __name__ == '__main__':
    run_bot(Player(), parse_args())
