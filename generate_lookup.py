"""
Preflop lookup table generator — Build4Good 2026 PokerBots

Game: No-Limit Texas Hold'em + Redraw
  - 400 starting chips, blinds 1/2
  - Streets: 0=preflop, 3=flop, 4=turn, 5=river
  - Each player may redraw ONE card (hole or board) once per hand, street < 5
  - Redraw is combined with a betting action: RedrawAction(type, index, action)

This script precomputes, for all 169 canonical preflop hands:
  - equity        : win probability vs random opponent (no redraw)
  - redraw_c0     : expected win prob if you redraw your higher-ranked hole card
  - redraw_c1     : expected win prob if you redraw your lower-ranked hole card
  - best_redraw   : max(redraw_c0, redraw_c1)
  - redraw_gain   : best_redraw - equity
  - best_redraw_card : 0 or 1 (which hole card index gives max gain)

Output: preflop_lookup.pkl
Requires: numpy only (no eval7 needed)
Usage: python3 generate_lookup.py
"""

import numpy as np
import pickle
import time

# ---------------------------------------------------------------------------
# Card encoding: card_int = rank * 4 + suit
# rank: 0='2' .. 12='A'  |  suit: 0='c' 1='d' 2='h' 3='s'
# ---------------------------------------------------------------------------

RANKS = '23456789TJQKA'
SUITS = 'cdhs'

def card_to_int(card_str):
    return RANKS.index(card_str[0]) * 4 + SUITS.index(card_str[1])

# Pre-generated full deck as integers (0..51)
FULL_DECK = np.arange(52, dtype=np.int32)

# All C(7,5) index combinations — shape (21, 5)
_7C5 = np.array([
    [0,1,2,3,4],[0,1,2,3,5],[0,1,2,3,6],[0,1,2,4,5],[0,1,2,4,6],
    [0,1,2,5,6],[0,1,3,4,5],[0,1,3,4,6],[0,1,3,5,6],[0,1,4,5,6],
    [0,2,3,4,5],[0,2,3,4,6],[0,2,3,5,6],[0,2,4,5,6],[0,3,4,5,6],
    [1,2,3,4,5],[1,2,3,4,6],[1,2,3,5,6],[1,2,4,5,6],[1,3,4,5,6],
    [2,3,4,5,6],
], dtype=np.int32)

RANK_VALS = np.arange(13, dtype=np.int32)
POWS5     = np.array([13**4, 13**3, 13**2, 13, 1], dtype=np.int64)


# ---------------------------------------------------------------------------
# Vectorized 5-card hand evaluator
# ---------------------------------------------------------------------------

def eval_5_batch(cards):
    """
    Evaluate a batch of 5-card hands.

    cards : (N, 5) int32 — card integers rank*4+suit
    Returns (N,) int64 scores; higher score = stronger hand.

    Hand categories (0–8):
      0 High card | 1 Pair | 2 Two pair | 3 Trips | 4 Straight
      5 Flush     | 6 Full house | 7 Quads | 8 Straight flush

    Tiebreaker within category: cards ordered by (count desc, rank desc),
    packed as base-13 number.  This gives correct ordering for all hand types.
    """
    cards = np.asarray(cards, dtype=np.int32)
    N     = len(cards)

    ranks = cards >> 2          # (N, 5),  0–12
    suits = cards & 3           # (N, 5),  0–3

    # --- Rank occurrence matrix ---
    # rc[i, r] = how many times rank r appears in hand i
    rc = (ranks[:, :, None] == RANK_VALS).sum(axis=1)   # (N, 13)

    # --- Tiebreaker: sort cards by (count desc, rank desc) ---
    cpc   = rc[np.arange(N)[:, None], ranks]             # (N, 5) count of each card's rank
    skey  = -(cpc * 100 + ranks)                         # (N, 5) lower value = higher priority
    ord_  = np.argsort(skey, axis=1, kind='stable')      # (N, 5)
    ordr  = ranks[np.arange(N)[:, None], ord_]           # (N, 5) ordered ranks
    tb    = (ordr.astype(np.int64) * POWS5).sum(axis=1)  # (N,)

    # --- Hand pattern flags ---
    has4   = (rc == 4).any(axis=1)
    has3   = (rc == 3).any(axis=1)
    npairs = (rc == 2).sum(axis=1)
    tp     = npairs >= 2
    hp     = npairs >= 1

    # Flush: all 5 suits identical
    is_fl  = (suits == suits[:, 0:1]).all(axis=1)

    # Straight: 5 consecutive ranks (including ace-low wheel A2345)
    sr     = np.sort(ranks, axis=1)          # (N, 5) ascending
    diffs  = np.diff(sr, axis=1)             # (N, 4)
    is_sn  = (diffs == 1).all(axis=1)
    is_wh  = ((sr[:, 0] == 0) & (sr[:, 1] == 1) & (sr[:, 2] == 2) &
               (sr[:, 3] == 3) & (sr[:, 4] == 12))
    is_st  = is_sn | is_wh
    is_sf  = is_st & is_fl

    # --- Category assignment (higher category overwrites lower) ---
    cat = np.zeros(N, dtype=np.int64)
    cat = np.where(hp & ~tp & ~has3 & ~has4 & ~is_st & ~is_fl, 1, cat)  # pair
    cat = np.where(tp & ~has3 & ~has4,                          2, cat)  # two pair
    cat = np.where(has3 & ~hp & ~has4,                          3, cat)  # trips
    cat = np.where(is_st & ~is_sf,                              4, cat)  # straight
    cat = np.where(is_fl & ~is_sf,                              5, cat)  # flush
    cat = np.where(has3 & hp & ~has4,                           6, cat)  # full house
    cat = np.where(has4,                                        7, cat)  # quads
    cat = np.where(is_sf,                                       8, cat)  # straight flush

    # For straights/SF: override tiebreaker with single straight-high rank
    # (wheel A2345 has effective high = rank of '5' = index 3)
    sh = np.where(is_wh, np.int64(3), sr[:, 4].astype(np.int64))
    tb = np.where(is_st, sh * POWS5[0], tb)

    return cat * np.int64(13 ** 5) + tb


def best_7_batch(c7):
    """
    c7 : (N, 7) int32 — find best 5-of-7 for each hand.
    Returns (N,) int64 scores.
    Memory-efficient: iterate over the 21 combos instead of allocating (N,21,5).
    """
    N    = len(c7)
    best = np.full(N, np.int64(-1))
    for ci in _7C5:
        s    = eval_5_batch(c7[:, ci])
        best = np.maximum(best, s)
    return best


# ---------------------------------------------------------------------------
# Vectorized random sampling without replacement
# ---------------------------------------------------------------------------

def sample_wr(rng, pool_size, k, n):
    """
    Draw n independent samples of size k from [0, pool_size) without replacement.
    Uses argpartition on uniform floats — fast for k << pool_size.
    Returns (n, k) int32 index array into the pool.
    """
    r = rng.random((n, pool_size), dtype=np.float32)
    return np.argpartition(r, k, axis=1)[:, :k].astype(np.int32)


# ---------------------------------------------------------------------------
# Monte Carlo equity functions
# ---------------------------------------------------------------------------

def mc_equity(hole_ints, board_ints, n, rng):
    """
    Base win-probability for hole_ints against a random opponent
    with a randomly completed board.

    hole_ints  : (2,) int32
    board_ints : (0–4,) int32
    """
    known    = set(int(x) for x in np.concatenate([hole_ints, board_ints]))
    pool     = np.array([i for i in range(52) if i not in known], dtype=np.int32)
    R        = len(pool)
    bn       = 5 - len(board_ints)
    need     = bn + 2                          # board completion + 2 opp cards

    idx      = sample_wr(rng, R, need, n)     # (n, need) indices into pool
    drawn    = pool[idx]                       # (n, need) card ints

    opp_hole = drawn[:, :2]                   # (n, 2)
    nb       = drawn[:, 2:]                   # (n, bn)

    hr       = np.tile(hole_ints,  (n, 1))    # (n, 2)
    if len(board_ints):
        br   = np.tile(board_ints, (n, 1))    # (n, len(board))
        fb   = np.concatenate([br, nb], axis=1)
    else:
        fb   = nb                              # (n, 5)

    my_s  = best_7_batch(np.concatenate([hr, fb], axis=1))   # (n,)
    opp_s = best_7_batch(np.concatenate([opp_hole, fb], axis=1))

    wins  = float(np.sum(my_s > opp_s)) + 0.5 * float(np.sum(my_s == opp_s))
    return wins / n


def mc_redraw_equity(hole_ints, board_ints, replace_idx, n, rng):
    """
    Expected win-probability after replacing hole_ints[replace_idx]
    with a randomly drawn card.

    Each trial draws: 1 replacement + board completion + 2 opp cards
    from the remaining deck (excluding both hole cards and board).
    """
    known    = set(int(x) for x in np.concatenate([hole_ints, board_ints]))
    pool     = np.array([i for i in range(52) if i not in known], dtype=np.int32)
    R        = len(pool)
    bn       = 5 - len(board_ints)
    need     = 1 + bn + 2                     # replacement + board + opp

    idx      = sample_wr(rng, R, need, n)
    drawn    = pool[idx]                       # (n, need)

    repl     = drawn[:, 0:1]                  # (n, 1)
    nb       = drawn[:, 1:1+bn]              # (n, bn)
    opp_hole = drawn[:, 1+bn:]               # (n, 2)

    hr       = np.tile(hole_ints, (n, 1))    # (n, 2)
    hr[:, replace_idx:replace_idx+1] = repl  # swap in replacement

    if len(board_ints):
        br   = np.tile(board_ints, (n, 1))
        fb   = np.concatenate([br, nb], axis=1)
    else:
        fb   = nb

    my_s  = best_7_batch(np.concatenate([hr, fb], axis=1))
    opp_s = best_7_batch(np.concatenate([opp_hole, fb], axis=1))

    wins  = float(np.sum(my_s > opp_s)) + 0.5 * float(np.sum(my_s == opp_s))
    return wins / n


# ---------------------------------------------------------------------------
# Canonical preflop hand generation
# ---------------------------------------------------------------------------

def canonical_hands():
    """Yield (key, [card1_str, card2_str]) for all 169 canonical preflop hands."""
    for i in range(12, -1, -1):          # Ace (12) down to 2 (0)
        r1 = RANKS[i]
        yield (f"{r1}{r1}", [f"{r1}c", f"{r1}d"])          # pocket pair
        for j in range(i - 1, -1, -1):
            r2 = RANKS[j]
            yield (f"{r1}{r2}s", [f"{r1}c", f"{r2}c"])     # suited
            yield (f"{r1}{r2}o", [f"{r1}c", f"{r2}d"])     # offsuit


def hand_to_key(cards):
    """Convert actual card strings to canonical key.  Works at runtime."""
    r0, s0 = cards[0][0], cards[0][1]
    r1, s1 = cards[1][0], cards[1][1]
    i0, i1 = RANKS.index(r0), RANKS.index(r1)
    if i0 < i1:
        r0, s0, i0, r1, s1, i1 = r1, s1, i1, r0, s0, i0
    if i0 == i1:
        return f"{r0}{r1}"
    return f"{r0}{r1}s" if s0 == s1 else f"{r0}{r1}o"


# ---------------------------------------------------------------------------
# Quick sanity-check (runs a few known hands through the evaluator)
# ---------------------------------------------------------------------------

def _run_tests():
    def h(*cards):
        return eval_5_batch(np.array([[card_to_int(c) for c in cards]], dtype=np.int32))[0]

    # Category checks
    assert h('Ac','Kc','Qc','Jc','Tc') > h('9c','8c','7c','6c','5c'), "SF ordering"
    assert h('As','Ad','Ah','Ac','2c') > h('Ks','Kd','Kh','Kc','Ac'), "Quads: AAAA > KKKK"
    assert h('Kc','Kd','Ks','Ac','Ad') > h('Qc','Qd','Qs','Ac','Ad'), "Full house: KKK > QQQ"
    assert h('Ks','Kd','Kh','Ac','Ad') > h('Qs','Qd','Qh','Ac','Ad'), "FH: KKKAA > QQQAA"
    assert h('Ks','Kd','Kh','Qc','Qd') > h('Qs','Qd','Qh','Ac','Ah'), "FH: KKKQQ > QQQAA (trips rank primary)"
    assert h('As','Ks','Qs','Js','9s') > h('Ac','Kc','Qc','Jc','8c'), "Flush ordering"
    assert h('Ac','Kd','Qs','Jh','Tc') > h('Kc','Qd','Js','Th','9c'), "Straight: A-high > K-high"
    assert h('2c','3d','4s','5h','Ac') > h('2c','3d','4s','5h','Kc'), "Wheel > non-wheel high"
    # wheel (A2345) < regular 6-high straight
    assert h('2c','3d','4s','5h','6c') > h('Ac','2d','3s','4h','5c'), "6-high str > wheel"
    assert h('Ac','Ad','Kc','Kd','Qc') > h('Ac','Ad','Qc','Qd','Kc'), "Two pair: AAKK > AAQQ"
    assert h('Ac','Ad','2c','3d','5h') > h('Kc','Kd','Qc','Jd','Th'), "Pair of A > pair of K"
    print("  All sanity checks passed.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    N     = 100_000
    rng   = np.random.default_rng(42)
    hands = list(canonical_hands())
    total = len(hands)
    assert total == 169, f"Expected 169 hands, got {total}"

    print("Build4Good 2026 — Preflop Lookup Table Generator")
    print(f"Hands: {total}  |  n={N:,} per run  |  numpy vectorized")
    print("Running sanity checks...", end=' ')
    _run_tests()

    lookup  = {}
    t_start = time.time()

    for idx, (key, cards) in enumerate(hands):
        t0         = time.time()
        hi         = np.array([card_to_int(c) for c in cards], dtype=np.int32)
        bi         = np.array([], dtype=np.int32)

        equity     = mc_equity(hi, bi, N, rng)
        redraw_c0  = mc_redraw_equity(hi, bi, 0, N, rng)
        redraw_c1  = mc_redraw_equity(hi, bi, 1, N, rng)

        best_r     = max(redraw_c0, redraw_c1)
        best_card  = 0 if redraw_c0 >= redraw_c1 else 1
        gain       = best_r - equity

        lookup[key] = {
            'equity':           round(equity,    5),
            'redraw_c0':        round(redraw_c0, 5),
            'redraw_c1':        round(redraw_c1, 5),
            'best_redraw':      round(best_r,    5),
            'redraw_gain':      round(gain,      5),
            'best_redraw_card': best_card,
        }

        elapsed  = time.time() - t_start
        per_hand = elapsed / (idx + 1)
        eta_min  = per_hand * (total - idx - 1) / 60

        print(
            f"[{idx+1:3d}/{total}] {key:6s}  "
            f"eq={equity:.4f}  rc0={redraw_c0:.4f}  rc1={redraw_c1:.4f}  "
            f"best={best_r:.4f}  gain={gain:+.4f}  "
            f"({time.time()-t0:.1f}s)  ETA {eta_min:.1f}m"
        )

    out = 'preflop_lookup.pkl'
    with open(out, 'wb') as f:
        pickle.dump(lookup, f)

    total_min = (time.time() - t_start) / 60
    print(f"\nSaved {len(lookup)} entries → {out}  (total {total_min:.1f} min)")

    # Print top/bottom 10 by equity for a sanity check
    ranked = sorted(lookup.items(), key=lambda x: x[1]['equity'], reverse=True)
    print("\nTop 10 preflop hands by equity:")
    for k, v in ranked[:10]:
        print(f"  {k:6s}  equity={v['equity']:.4f}  redraw_gain={v['redraw_gain']:+.4f}")
    print("Bottom 10:")
    for k, v in ranked[-10:]:
        print(f"  {k:6s}  equity={v['equity']:.4f}  redraw_gain={v['redraw_gain']:+.4f}")


if __name__ == '__main__':
    main()
