# Poker Bot Strategy: Four-Phase Redraw Framework

## Game Parameters

| Parameter | Value |
|---|---|
| Format | Heads-up No-Limit Hold'em + Redraw |
| Hands per match | 1000 |
| Starting chips per hand | 250 (reset every hand) |
| Blinds | 2 / 5 |
| Effective stack | 50 BB |
| Time budget | 180 seconds for the entire match |
| Time per hand (avg) | ~0.18 seconds across all streets |
| Redraw limit | Once per player per hand, before river (street < 5) |

## Redraw Mechanic — Full Understanding

A redraw replaces **one card** — either one of your two private hole cards, or one of the revealed community (board) cards. The replaced card is drawn randomly from the remaining deck. The old card that was swapped out is **revealed to the opponent**.

Critical details:

- **Bundled with a betting action.** A redraw is not a standalone action. You must simultaneously choose a betting action (fold, check, call, or raise) AND a redraw target. The `RedrawAction(target_type, target_index, action)` packages both together.
- **Once per hand, before the river.** Each player gets exactly one redraw per hand. It can be used on the flop (street 3) or the turn (street 4), but not preflop (street 0) or on the river (street 5).
- **Board card redraws affect both players.** When anyone (us or the opponent) redraws a community card, the board itself changes. This means a board redraw can improve *or destroy* either player's hand. A board redraw is a fundamentally different and more volatile action than a hole card redraw.
- **The discarded card is public information.** Both players see what card was removed, regardless of whether it was a hole card or board card.

### Two Types of Redraw — Very Different Implications

**Hole card redraw:** The player swaps one of their private cards. The board stays the same. The opponent sees the discarded hole card, which leaks information about the player's private hand. The replacement is drawn from the deck and is private to the player.

- Effect: Only changes the redrawn player's hand.
- Information leak: Opponent learns one card that *was* in the player's hand.
- Strategic use: Improving a weak kicker, chasing a draw by replacing an irrelevant card.

**Board card redraw:** The player swaps one of the community cards. The entire board texture changes for *both* players. The opponent sees which board card was removed (they already knew it since it was public), and a new random board card replaces it.

- Effect: Changes both players' hands simultaneously. Can dramatically shift equity for either player in either direction.
- Information leak: The opponent learns that the redrawn player disliked that particular board card. This is a strong signal — it means that card was likely helping the opponent more than the redrawn player, or at least not helping the redrawn player.
- Strategic use: Destroying an opponent's likely made hand or draw, removing a card that pairs the board when you don't have trips, reshaping the board to be more favorable to your hole cards.
- Risk: The replacement card is random and could be even worse for you, or could give the opponent something even stronger.

---

## Core Idea

We decompose every decision point into one of four game phases based on redraw state. Each phase has a distinct strategy because redraw usage fundamentally changes the information landscape, each player's remaining optionality, and (in the case of board redraws) potentially the board itself.

| Phase | We redrawn? | Opponent redrawn? | Key characteristic |
|---|---|---|---|
| **Phase 1** | No | No | Standard NLHE + option to initiate redraw |
| **Phase 2** | No | Yes | **Primary edge.** We have info + optionality advantage |
| **Phase 3** | Yes | No | We are transparent; opponent has optionality |
| **Phase 4** | Yes | Yes | Simplified NLHE with extra range info on both sides |

---

## Phase 1: Neither Player Has Redrawn

### Situation

This is the default state at the start of every hand and on every street until someone redraws. The game is standard heads-up NLHE, except both players carry a latent redraw option.

### Strategy

Play a solid, tight-aggressive heads-up strategy.

**Preflop:**
- Open-raise to 2.5x (12-13 chips) from the button/SB with a standard heads-up opening range (~60-70% of hands).
- 3-bet a polarized range from BB: premium hands and some suited connectors/small pairs as bluffs.
- At 50BB effective, avoid getting into bloated 4-bet pots without premiums.
- No redraws are possible preflop (street 0), so this is pure standard NLHE.

**Post-flop:**
- Use a simplified hand-strength bucketing system. Categorize your hand as: strong (top pair+), medium (middle pair, decent draws), weak (bottom pair, no draw), or air.
- C-bet ~60-70% of flops as the preflop aggressor, sizing around 33-50% pot.
- On turn, bet for value with strong hands, check-call with medium hands, and give up or bluff selectively with air.

**Redraw evaluation (proactive):**
- At each post-flop decision point (flop, turn), evaluate whether to bundle a redraw with our betting action.
- Consider both hole card and board card redraws as candidates (see Redraw Decision Engine below).
- Only initiate a redraw when the expected equity improvement exceeds a threshold that accounts for the information cost and the volatility (especially for board redraws).
- Avoid proactive redraws when you already have a strong hand — the information leak isn't worth the marginal improvement.
- Board card redraws should have a higher threshold than hole card redraws because of their volatility — they change the game for both players.

### When to leave Phase 1

- If we decide to redraw → transition to Phase 3.
- If opponent redraws → transition to Phase 2.
- If we reach the river with no redraws → stay in Phase 1 (redraw is no longer possible, play standard NLHE river strategy).

---

## Phase 2: Opponent Has Redrawn, We Have Not

### Situation

**This is where we expect to gain the most edge.** The opponent has used their redraw, which means:

1. **We gain information.** We see what card they discarded (hole or board).
2. **They have no redraw remaining.** Their optionality is gone.
3. **We still have our redraw available.** We retain maximum flexibility.
4. **If they redrawn a board card, the board itself has changed.** We must re-evaluate our hand against the new board.

This is an asymmetric information + asymmetric optionality situation, and both asymmetries favor us.

### Responding to an Opponent Hole Card Redraw

When the opponent swaps one of their hole cards, the board stays the same but we learn a lot about their private hand.

**What the discard tells us:**
- The discarded card was their weaker card (usually). If they throw away a King, they likely don't have KK — they had K-x where the King wasn't working well with the board.
- Eliminate all hands containing that exact card from their range.
- Their remaining hand is: (one kept card we can partially infer) + (one random replacement from the deck). This is significantly weaker on average than a hand they voluntarily continued with preflop.
- If they discard a low card (2-7), they're probably keeping a high card. If they discard a high card, they might be chasing a draw where that card was irrelevant.

**How to exploit:**
- Their hand is effectively (kept card + random card), which is worse on average than a standard postflop holding. Increase aggression.
- Bet for value with hands you might normally check. Their range is capped and partially random.
- Bluff more often — they've shown weakness by redrawing, and their replacement card misses frequently.
- Our hand is unchanged, so our equity assessment only needs to account for their weakened range.

**Our redraw decision:**
- We still have our redraw. Evaluate whether to use it based on the Monte Carlo engine.
- Since the opponent has already redrawn, the information cost of our redraw is lower — they can't react to our discard by redrawing themselves. This means our threshold for redrawing should be lower (see Redraw Decision Engine).
- However, they can still adjust their betting strategy based on what we discard. So the information cost isn't zero.

### Responding to an Opponent Board Card Redraw

This is a fundamentally different and more complex situation. The opponent has changed the community cards, which affects *our hand too*.

**Immediate impact:**
- **Re-evaluate our entire hand.** The board is different now. A hand that was top pair might now be nothing. A hand that was a flush draw might now be a made flush or might have lost the draw entirely.
- **We see which board card they removed.** This tells us that card was bad for them (or good for us). If they removed the card that was giving us top pair, they probably read us correctly. If they removed a card that completed a common draw, they probably didn't have that draw.

**What the discard tells us:**
- The removed board card was helping us more than them, OR it was enabling a draw they didn't have, OR it was creating a board texture they couldn't connect with.
- Think about it from their perspective: they chose to change the board rather than their own hand. This means they believed the board texture was a bigger problem for them than their hole cards.
- If they removed a high card from the board, they probably have low-to-medium hole cards that couldn't connect. If they removed a suited card, they probably don't have that suit.

**How to exploit:**
- Re-evaluate our hand against the new board FIRST. Before any strategic thinking, calculate our new hand strength.
- If the new board is good for us: bet aggressively. They gambled on the board change and it might have backfired.
- If the new board is bad for us: consider using our own redraw (hole card swap) to adapt to the new board. This is a key advantage — they changed the board, and we still have a redraw to adjust.
- Their hole cards are unchanged (they swapped a board card, not a hole card), so our preflop-based range estimate for their private hand still holds. Combine this with the signal from which board card they removed.

**Our redraw decision after a board redraw:**
- This is where retaining our redraw is most valuable. The board has shifted, and our hole cards may no longer fit well. We can use our redraw to adapt.
- Run Monte Carlo on swapping each of our hole cards given the NEW board.
- The threshold for using our redraw here should be the lowest of any phase, because the board change may have made our hand significantly worse and we have a chance to fix it.

### Concrete Strategy in Phase 2 (Both Redraw Types)

**When we have a strong hand on the current board:**
- Do NOT redraw. Our hand is already good.
- Bet for value. Size up (60-80% pot) against an opponent who has shown weakness via redraw.
- If they redrawn a board card, verify our hand is still strong on the new board before committing chips.

**When we have a medium hand:**
- If opponent redrawn a hole card: play for thin value. Their (kept + random) range is weak.
- If opponent redrawn a board card: re-evaluate. Our medium hand might now be strong or weak depending on the new board card. Adjust accordingly.
- Consider redrawing our weaker hole card if Monte Carlo shows meaningful equity gain.

**When we have a weak hand or air:**
- Best time to consider our own redraw. We have little to lose.
- If opponent redrawn a hole card: consider bluffing (they're weak) OR redrawing ourselves to try to make a hand.
- If opponent redrawn a board card: the new board might have helped us accidentally. Check before deciding.
- If even after optimal redraw our expected equity is poor, fold rather than burning chips.

### Monte Carlo Simulation for Phase 2 Redraw Decision

When deciding whether to use our redraw in Phase 2:

```
dead_cards = our_hole_cards + current_board + [opponent_discard]
remaining_deck = full_52 - dead_cards

For each possible redraw target (hole[0], hole[1]):
    # We typically only consider hole card redraws here.
    # Board card redraws in Phase 2 are rare — the opponent just changed
    # the board, and changing it again is high-variance.
    
    For K Monte Carlo samples (K ≈ 100-200):
        1. Sample a replacement card from remaining_deck
        2. Build our new hand with the replacement
        3. Estimate opponent range:
           - If they redrawn hole card: (unknown kept card) + (random card)
           - If they redrawn board card: original preflop range (hole cards unchanged)
        4. Compute equity of our new hand vs opponent range on current board
    Average equity → expected_equity_after_redraw[target]

Compare: max(expected_equity_after_redraw) vs current_equity_without_redraw
Apply Phase 2 threshold (lower than Phase 1 — see Redraw Decision Engine)
```

### Why This Phase Is Our Biggest Edge

Most bots will either never redraw (leaving value on the table) or redraw naively without exploiting the information asymmetry. By treating the opponent's redraw as a major information event and retaining our own redraw as a response option, we can make significantly better decisions.

The core asymmetries working in our favor:
- We have information they leaked; they don't have equivalent info on us.
- We have optionality (our redraw) they've spent.
- If they redrawn a hole card, their hand is partially random and therefore weak.
- If they redrawn a board card, we can adapt to the new board with our own redraw.

---

## Phase 3: We Have Redrawn, Opponent Has Not

### Situation

We've used our redraw, so the opponent sees our discarded card. They still have their redraw available. The information and optionality disadvantage is now ours.

### Key Difference: What Did We Redraw?

**If we redrawn a hole card:**
- The opponent knows one card we discarded from our hand. They can narrow our range.
- Our hand is now (kept card + replacement). If we hit something strong, play it; if not, we're in a tough spot with a transparent range.
- The opponent might react by playing more aggressively against our narrowed range, or they might use their redraw to further improve their position.

**If we redrawn a board card:**
- We changed the community cards. The opponent needs to re-evaluate their own hand too.
- They know we disliked the old board. But the new board might have helped or hurt them — they need to figure this out.
- They still have their redraw to respond. They might swap a hole card to adapt to the new board we created, similar to what we'd do in Phase 2.
- This sub-case is slightly less bad for us than a hole card redraw, because we didn't leak private hand information — we leaked board preference information, which is less directly exploitable.

### Strategy

Play straightforward, honest poker. We can't afford to get fancy.

- Our range is more transparent. Avoid bluffing in spots where our discard makes a bluff unbelievable.
- The opponent still has redraw optionality, so their effective equity is slightly higher than raw hand strength suggests.
- Bet for value when we have it, check-fold when we don't.
- Size bets slightly smaller than Phase 1 — we're more likely to get looked up since the opponent has extra information to make good calls.
- Be wary of the opponent using their redraw in response to ours. If they redraw after we did, we transition to Phase 4.

**When to enter Phase 3:**
- Only when we assessed in Phase 1 that the redraw was clearly +EV enough to justify the information and optionality cost. This should happen infrequently — maybe 15-25% of hands where we see a flop.

---

## Phase 4: Both Players Have Redrawn

### Situation

Both redraws are spent. Both players have seen one of the other's discards. No one has remaining optionality. This is the simplest phase.

### Strategy

This is essentially standard NLHE with bonus information on both sides.

- Play solid value-oriented poker.
- Use both discards to refine hand reads. Apply the same range-narrowing logic from Phase 2, but for both players.
- No redraw evaluation needed — just play the hand out.
- Lean toward slightly more aggressive play than Phase 3, since the opponent no longer has the redraw threat over us. The information disadvantage is now symmetric.
- If both players redrawn board cards, the board may have changed twice — make sure the hand evaluation is based on the current board state, not any prior version.

---

## Redraw Decision Engine (Shared Across Phases)

This module is called whenever we're evaluating whether to use our redraw. It runs on the flop and turn only (street 3 and 4).

### Inputs
- Our hole cards (2 cards)
- Current board (3 cards on flop, 4 on turn)
- Known dead cards (opponent's discard if in Phase 2, previously revealed cards)
- Opponent's estimated range (simplified)
- Current pot size and stack depths
- Current phase (affects threshold)

### Algorithm

```
current_equity = evaluate_equity(our_hand, board, opponent_range, dead_cards)

best_redraw = None
best_equity = current_equity

# --- Evaluate hole card redraws ---
for hole_index in [0, 1]:
    equities = []
    remaining_deck = full_52 - our_hand - board - dead_cards
    for replacement in sample(remaining_deck, K=150):
        new_hand = replace_hole_card(our_hand, hole_index, replacement)
        eq = evaluate_equity(new_hand, board, opponent_range, dead_cards)
        equities.append(eq)
    avg_eq = mean(equities)
    if avg_eq > best_equity:
        best_equity = avg_eq
        best_redraw = ('hole', hole_index)

# --- Evaluate board card redraws ---
for board_index in range(len(board)):  # 0..2 on flop, 0..3 on turn
    equities = []
    remaining_deck = full_52 - our_hand - board - dead_cards
    for replacement in sample(remaining_deck, K=150):
        new_board = replace_board_card(board, board_index, replacement)
        eq = evaluate_equity(our_hand, new_board, opponent_range, dead_cards)
        equities.append(eq)
    avg_eq = mean(equities)
    if avg_eq > best_equity:
        best_equity = avg_eq
        best_redraw = ('board', board_index)

equity_gain = best_equity - current_equity

# --- Phase-dependent thresholds ---
# Phase 1: High bar — we're giving up info + optionality to an opponent
#           who still has their redraw
# Phase 2 (after opp hole redraw): Lower bar — info cost is reduced,
#           opponent can't redraw in response
# Phase 2 (after opp board redraw): Lowest bar — the board shifted and
#           we may need to adapt; opponent already spent their redraw

if phase == 1:
    threshold = 0.12   # 12% equity gain needed
elif phase == 2 and opp_redrawn_type == 'hole':
    threshold = 0.08   # 8% — favorable position, lower cost
elif phase == 2 and opp_redrawn_type == 'board':
    threshold = 0.05   # 5% — board shifted, we need to adapt

if equity_gain > threshold:
    return RedrawAction(best_redraw.type, best_redraw.index, betting_action)
else:
    return betting_action  # don't redraw
```

### Quick Heuristics (When Time Is Tight)

**Hole card redraw candidates:**
- Swap the hole card contributing least to hand strength.
- Never swap a card that's part of a made pair or better.
- Good targets: a low kicker when you have one pair, an offsuit card when one card from a flush.

**Board card redraw candidates:**
- Swap a board card that is clearly helping the opponent's likely range more than yours.
- Example: Board has three hearts, you have no hearts → swap one of the hearts.
- Example: Board pairs and you don't have trips → swap the paired card if you think the opponent benefits from it.
- Avoid swapping board cards that are part of your own made hand.
- Board redraws are higher variance — the replacement is random and changes the game for both players. Use sparingly and only when the current board is clearly terrible for you.

---

## Opponent Modeling (Lightweight)

Over 1000 hands, build a simple opponent profile by tracking:

- **Redraw frequency:** How often do they redraw? Do they prefer hole or board redraws? On which streets? A player who redraws often is speculating frequently; a player who rarely redraws is playing more standard NLHE.
- **Redraw type preference:** Hole card redraws are conservative (improve your hand, keep the board). Board card redraws are aggressive (reshape the game). An opponent who board-redraws frequently is trying to disrupt — play tighter against them post-redraw since the board is unpredictable.
- **Post-redraw aggression:** When they redraw and then bet big, did they tend to have strong hands at showdown? Calibrates how much respect to give their post-redraw bets.
- **Response to our redraws:** Do they tighten up or stay the same? If they don't adjust, we can redraw more freely.

Store these as simple counters and ratios. No heavy computation needed.

---

## Time Budget Strategy

With 180 seconds across 1000 hands:

| Component | Time per hand | Notes |
|---|---|---|
| Phase detection + routing | <0.1ms | Trivial if/else logic |
| Preflop decision | <0.5ms | Lookup table |
| Post-flop hand evaluation | <1ms | Fast evaluator call |
| Redraw Monte Carlo (when triggered) | <15ms | ~150 samples × 5-7 targets (hole + board) |
| Re-evaluation after board change | <1ms | Re-run hand evaluator on new board |
| Opponent model update | <0.1ms | Counter increments |
| **Total per hand** | **<18ms** | **Well within budget** |

At 18ms per hand × 1000 hands = 18 seconds total, using only ~10% of the time budget. Plenty of headroom.

---

## Implementation Checklist

### Must-Have (Core — build first)

- [ ] Hand strength evaluator (use `pkrbot` or build with eval logic)
- [ ] Phase detection: track `we_redrawn` and `opp_redrawn` booleans per hand, plus `opp_redraw_type` ('hole' or 'board') and `opp_discard` (the revealed card)
- [ ] Board state tracking: always work with the *current* board, which may have been modified by a board card redraw
- [ ] Phase 1 baseline: tight-aggressive preflop ranges, simple postflop bucketing
- [ ] Phase 2 full implementation: discard tracking, range narrowing, Monte Carlo redraw decision with both hole and board targets, aggression adjustment
- [ ] Redraw decision engine with Monte Carlo sampling (hole + board card targets)
- [ ] Action validation: always check `round_state.legal_actions()` before returning
- [ ] Proper bundling: always wrap redraw with a legal betting action via `RedrawAction(target_type, target_index, action)`

### Should-Have (Edge — build second)

- [ ] Differentiated Phase 2 response for hole vs board opponent redraws
- [ ] Opponent modeling: redraw frequency, type preference, post-redraw aggression
- [ ] Adaptive thresholds: adjust redraw equity threshold based on opponent tendencies
- [ ] Phase 3 adjustments: tighter play, smaller sizing, sub-strategies for "we redrawn hole" vs "we redrawn board"

### Nice-to-Have (Polish — build if time allows)

- [ ] Phase 4 double-information exploitation
- [ ] Bluff frequency calibration based on opponent fold-to-bet stats
- [ ] Street-specific redraw timing optimization (flop vs turn EV comparison)
- [ ] Board card redraw as disruption: proactively reshaping the board when we detect the opponent has a strong draw

---

## Summary

The core thesis: **play solid standard poker as a baseline, and extract maximum value when the opponent redraws.** Phase 2 is where we win — by treating the opponent's redraw as a weakness signal, narrowing their range from the discard, leveraging our retained optionality, and adapting to board changes with our own redraw.

The key distinction between hole card and board card redraws runs through every phase. When someone redraws a hole card, only their private hand changes. When someone redraws a board card, the shared reality of the hand shifts for both players — this is higher variance, more disruptive, and creates different strategic opportunities depending on which side of it you're on.
