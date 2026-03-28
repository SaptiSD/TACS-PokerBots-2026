'''
TACS PokerBots 2026 — Champion Bot
Advanced strategy for Hold'em + Redraw variant.
Uses Monte Carlo hand strength evaluation, redraw optimization,
opponent modeling, and pot-odds-based decision making.
'''
import random
import time
from skeleton.actions import FoldAction, CallAction, CheckAction, RaiseAction, RedrawAction
from skeleton.states import GameState, TerminalState, RoundState, NUM_ROUNDS, STARTING_STACK, BIG_BLIND, SMALL_BLIND
from skeleton.bot import Bot
from skeleton.runner import parse_args, run_bot

# ─── Constants ───────────────────────────────────────────────────────────────
RANKS = '23456789TJQKA'
SUITS = 'cdhs'
ALL_CARDS = [r + s for r in RANKS for s in SUITS]

# Preflop hand strength tiers (heads-up, 0.0=worst, 1.0=best)
# Pocket pairs
PAIR_STRENGTH = {
    'A': 0.98, 'K': 0.95, 'Q': 0.92, 'J': 0.89, 'T': 0.86,
    '9': 0.78, '8': 0.74, '7': 0.70, '6': 0.66, '5': 0.62,
    '4': 0.58, '3': 0.55, '2': 0.52
}

# Monte Carlo simulation budget control
MC_SIMS_PREFLOP = 200
MC_SIMS_FLOP = 300
MC_SIMS_TURN = 400
MC_SIMS_RIVER = 500
MC_SIMS_REDRAW = 100  # per redraw candidate


def rank_value(card_str):
    """Returns numeric rank value 0-12 for a card string like 'Ah'."""
    if not card_str or card_str == '??' or len(card_str) < 2:
        return -1
    r = card_str[0]
    return RANKS.index(r) if r in RANKS else -1


def card_to_str(card):
    """Converts a card object or string to string representation."""
    return str(card) if not isinstance(card, str) else card


def make_deck_minus(exclude_strs):
    """Returns a list of card strings NOT in exclude_strs."""
    exclude_set = set(exclude_strs)
    return [c for c in ALL_CARDS if c not in exclude_set]


import pkrbot
_CARD_CACHE = {s: pkrbot.Card(s) for s in ALL_CARDS}

def evaluate_hand_strings(card_strings):
    """Evaluates a 5-7 card hand given as string list. Returns int score (higher=better)."""
    cards = [_CARD_CACHE[s] for s in card_strings]
    return pkrbot.evaluate(cards)


def monte_carlo_win_rate(my_hand, board, num_sims, known_opp_cards=None):
    """
    Estimates win rate via Monte Carlo simulation.
    my_hand: list of card strings (our hole cards, possibly with '??')
    board: list of card strings (community cards, possibly with '??')
    known_opp_cards: partial info about opponent's hand from redraw reveals
    Returns: float in [0.0, 1.0]
    """
    # Filter out unknown cards
    my_known = [c for c in my_hand if c and c != '??']
    board_known = [c for c in board if c and c != '??']

    if len(my_known) < 2:
        # We have an unknown hole card from our own redraw — can't evaluate well
        # In practice the runner replaces our own redraw with the new card,
        # so this case shouldn't happen for our own hand.
        # But be safe: return neutral
        return 0.5

    # Cards we definitely know are out of the deck
    exclude = set(my_known + board_known)
    if known_opp_cards:
        exclude.update(c for c in known_opp_cards if c and c != '??')

    remaining = [c for c in ALL_CARDS if c not in exclude]

    # How many board cards still need to be dealt
    board_to_deal = 5 - len(board_known)
    # Opponent needs 2 cards (minus any known)
    opp_known_count = len(known_opp_cards) if known_opp_cards else 0

    wins = 0
    ties = 0
    total = 0

    for _ in range(num_sims):
        random.shuffle(remaining)
        idx = 0

        # Deal opponent's cards
        opp_hand = list(known_opp_cards) if known_opp_cards else []
        opp_need = 2 - len(opp_hand)
        for _ in range(opp_need):
            if idx < len(remaining):
                opp_hand.append(remaining[idx])
                idx += 1

        # Deal remaining board
        sim_board = list(board_known)
        for _ in range(board_to_deal):
            if idx < len(remaining):
                sim_board.append(remaining[idx])
                idx += 1

        # Evaluate
        try:
            my_score = evaluate_hand_strings(my_known + sim_board)
            opp_score = evaluate_hand_strings(opp_hand + sim_board)
            if my_score > opp_score:
                wins += 1
            elif my_score == opp_score:
                ties += 1
            total += 1
        except Exception:
            continue

    if total == 0:
        return 0.5
    return (wins + 0.5 * ties) / total


def preflop_hand_strength(hand):
    """Quick preflop hand strength estimate without MC (for speed)."""
    if len(hand) < 2:
        return 0.3
    c1, c2 = card_to_str(hand[0]), card_to_str(hand[1])
    r1, r2 = rank_value(c1), rank_value(c2)

    if r1 < 0 or r2 < 0:
        return 0.3

    # Pocket pair
    if r1 == r2:
        return PAIR_STRENGTH.get(c1[0], 0.5)

    suited = (len(c1) >= 2 and len(c2) >= 2 and c1[1] == c2[1])
    high = max(r1, r2)
    low = min(r1, r2)
    gap = high - low

    # Base strength from high card
    strength = 0.20 + high * 0.045

    # Suited bonus
    if suited:
        strength += 0.04

    # Connectedness bonus
    if gap == 1:
        strength += 0.03
    elif gap == 2:
        strength += 0.01

    # Both broadway (T+)
    if low >= 8:  # T is index 8
        strength += 0.06

    # Ace-high
    if high == 12:
        strength += 0.05
        if low >= 8:  # AT+
            strength += 0.05

    # King-high
    if high == 11:
        strength += 0.02
        if low >= 8:
            strength += 0.03

    return min(strength, 0.95)


class OpponentModel:
    """Tracks opponent behavior patterns across a match."""

    def __init__(self):
        self.hands_played = 0
        self.vpip_count = 0         # Voluntarily put money in pot
        self.pfr_count = 0          # Preflop raise
        self.fold_to_raise = 0      # Times folded facing a raise
        self.raise_faced = 0        # Times faced a raise
        self.total_raises = 0       # Opponent's total raises
        self.total_actions = 0      # Total actions we've observed
        self.redraw_count = 0       # Times opponent used redraw
        self.revealed_cards = []    # Cards revealed from opponent's redraws
        self.aggression_postflop = 0  # Postflop raises/bets
        self.postflop_actions = 0   # Total postflop actions
        self.showdown_wins = 0
        self.showdown_total = 0

        # Recent history for adaptation (last N hands)
        self.recent_results = []    # +/- deltas
        self.recent_window = 50

    @property
    def vpip(self):
        return self.vpip_count / max(1, self.hands_played)

    @property
    def pfr(self):
        return self.pfr_count / max(1, self.hands_played)

    @property
    def fold_rate(self):
        return self.fold_to_raise / max(1, self.raise_faced)

    @property
    def aggression_factor(self):
        return self.total_raises / max(1, self.total_actions)

    @property
    def postflop_aggression(self):
        return self.aggression_postflop / max(1, self.postflop_actions)

    @property
    def redraw_frequency(self):
        return self.redraw_count / max(1, self.hands_played)

    @property
    def showdown_win_rate(self):
        return self.showdown_wins / max(1, self.showdown_total)

    def is_passive(self):
        return self.aggression_factor < 0.25

    def is_aggressive(self):
        return self.aggression_factor > 0.45

    def is_tight(self):
        return self.vpip < 0.55

    def is_loose(self):
        return self.vpip > 0.75

    def folds_to_pressure(self):
        return self.fold_rate > 0.45 and self.raise_faced >= 10

    def recent_trend(self):
        """Returns average delta over recent hands. Positive = we're winning."""
        if not self.recent_results:
            return 0
        window = self.recent_results[-self.recent_window:]
        return sum(window) / len(window)


class Player(Bot):
    '''
    Champion poker bot with Monte Carlo evaluation, redraw optimization,
    opponent modeling, and adaptive strategy.
    '''

    def __init__(self):
        self.opp_model = OpponentModel()
        self.round_num = 0
        self.time_budget_remaining = 60.0  # Will be updated from game_state
        self.my_bankroll = 0

        # Per-hand tracking
        self.my_preflop_hand_str = 0.0
        self.has_raised_this_street = False
        self.street_actions = 0
        self.opp_revealed_cards = []
        self.used_redraw = False

    def handle_new_round(self, game_state, round_state, active):
        self.round_num = game_state.round_num
        self.time_budget_remaining = game_state.game_clock
        self.my_bankroll = game_state.bankroll
        self.opp_model.hands_played += 1

        # Per-hand reset
        self.has_raised_this_street = False
        self.street_actions = 0
        self.opp_revealed_cards = []
        self.used_redraw = False

        # Quick preflop assessment
        my_cards = round_state.hands[active]
        self.my_preflop_hand_str = preflop_hand_strength(my_cards)

    def handle_round_over(self, game_state, terminal_state, active):
        my_delta = terminal_state.deltas[active]
        self.opp_model.recent_results.append(my_delta)

        # Track showdown results
        prev = terminal_state.previous_state
        if prev and hasattr(prev, 'street') and prev.street == 5:
            self.opp_model.showdown_total += 1
            if my_delta > 0:
                self.opp_model.showdown_wins += 1

    def _get_mc_sims(self, street):
        """Adaptive simulation count based on remaining time budget."""
        # Average time per hand remaining
        rounds_left = max(1, NUM_ROUNDS - self.round_num + 1)
        time_per_hand = self.time_budget_remaining / rounds_left

        # Each hand has ~4 decision points on average
        time_per_decision = time_per_hand / 4.0

        # Scale MC sims to fit time budget (rough: ~0.0003s per sim)
        max_sims_for_time = max(30, int(time_per_decision / 0.0003))

        base = {0: MC_SIMS_PREFLOP, 3: MC_SIMS_FLOP, 4: MC_SIMS_TURN, 5: MC_SIMS_RIVER}
        target = base.get(street, MC_SIMS_FLOP)

        return min(target, max_sims_for_time)

    def _evaluate_redraw_options(self, round_state, active):
        """
        Evaluates all possible redraw targets and returns the best one.
        Returns: (should_redraw, target_type, target_index, expected_improvement)
        """
        my_hand = [card_to_str(c) for c in round_state.hands[active]]
        board = [card_to_str(c) for c in round_state.board]
        street = round_state.street

        # Current strength
        opp_info = self.opp_revealed_cards if self.opp_revealed_cards else None
        current_wr = monte_carlo_win_rate(my_hand, board, 30, opp_info)

        best_option = None
        best_improvement = -999

        # Evaluate redrawing each hole card
        for idx in range(2):
            card = my_hand[idx]
            if not card or card == '??':
                continue

            # Simulate: remove this card, what's our expected strength with a random replacement?
            remaining_hand = [my_hand[1 - idx]]
            exclude = set(my_hand + board)
            if opp_info:
                exclude.update(c for c in opp_info if c and c != '??')
            deck = [c for c in ALL_CARDS if c not in exclude]

            # Sample replacement cards and average their win rates
            sample_size = min(5, len(deck))
            if sample_size == 0:
                continue
            sample = random.sample(deck, sample_size)

            total_wr = 0
            for replacement in sample:
                new_hand = list(my_hand)
                new_hand[idx] = replacement
                wr = monte_carlo_win_rate(new_hand, board, 15, opp_info)
                total_wr += wr

            avg_wr = total_wr / sample_size
            improvement = avg_wr - current_wr

            # Penalize information leak — opponent sees our discarded card
            # High card reveals hurt more
            info_penalty = rank_value(card) * 0.002
            adjusted_improvement = improvement - info_penalty

            if adjusted_improvement > best_improvement:
                best_improvement = adjusted_improvement
                best_option = ('hole', idx)

        # Evaluate redrawing board cards
        board_limit = -1
        if street == 3:
            board_limit = 2
        elif street == 4:
            board_limit = 3

        for idx in range(min(len(board), board_limit + 1)):
            card = board[idx]
            if not card or card == '??':
                continue

            exclude = set(my_hand + board)
            if opp_info:
                exclude.update(c for c in opp_info if c and c != '??')
            deck = [c for c in ALL_CARDS if c not in exclude]

            sample_size = min(4, len(deck))
            if sample_size == 0:
                continue
            sample = random.sample(deck, sample_size)

            total_wr = 0
            for replacement in sample:
                new_board = list(board)
                new_board[idx] = replacement
                wr = monte_carlo_win_rate(my_hand, new_board, 15, opp_info)
                total_wr += wr

            avg_wr = total_wr / sample_size
            improvement = avg_wr - current_wr

            # Board redraw has lower info penalty (card is already public)
            # but it also helps opponent potentially
            adjusted_improvement = improvement * 0.85  # discount because opponent benefits too

            if adjusted_improvement > best_improvement:
                best_improvement = adjusted_improvement
                best_option = ('board', idx)

        # Only redraw if meaningful improvement expected
        threshold = 0.04  # Need at least 4% win rate improvement
        if best_option and best_improvement > threshold:
            return True, best_option[0], best_option[1], best_improvement

        return False, None, None, 0.0

    def _get_pot_size(self, round_state):
        """Calculate current pot size."""
        return 2 * STARTING_STACK - round_state.stacks[0] - round_state.stacks[1]

    def _bet_sizing(self, round_state, active, win_rate):
        """Determines optimal raise amount."""
        pot = self._get_pot_size(round_state)
        min_raise, max_raise = round_state.raise_bounds()
        my_stack = round_state.stacks[active]

        # Stack-to-pot ratio
        spr = my_stack / max(1, pot)

        if win_rate > 0.85:
            # Monster hand — go big or all-in
            if spr < 2:
                return max_raise  # All-in when shallow
            target = int(pot * 1.0)  # Pot-size bet
        elif win_rate > 0.70:
            # Strong hand — value bet
            target = int(pot * 0.70)
        elif win_rate > 0.55:
            # Decent hand — medium bet
            target = int(pot * 0.50)
        else:
            # Marginal / bluff — small bet
            target = int(pot * 0.35)

        # Adapt vs opponent
        if self.opp_model.folds_to_pressure() and win_rate > 0.40:
            # Opponent folds a lot — increase sizing
            target = int(target * 1.3)
        elif self.opp_model.is_passive() and win_rate > 0.60:
            # Passive opponent — value bet larger
            target = int(target * 1.2)

        # Clamp to legal bounds
        amount = max(min_raise, min(target, max_raise))
        return amount

    def get_action(self, game_state, round_state, active):
        '''Main decision function.'''
        legal_actions = round_state.legal_actions()
        street = round_state.street
        my_pip = round_state.pips[active]
        opp_pip = round_state.pips[1 - active]
        continue_cost = opp_pip - my_pip
        my_stack = round_state.stacks[active]
        pot = self._get_pot_size(round_state)

        # ─── Compute hand strength ───────────────────────────────────
        my_hand = [card_to_str(c) for c in round_state.hands[active]]
        board = [card_to_str(c) for c in round_state.board]

        if street == 0:
            # Preflop: use fast table lookup
            win_rate = self.my_preflop_hand_str
        else:
            # Post-flop: Monte Carlo
            opp_info = self.opp_revealed_cards if self.opp_revealed_cards else None
            num_sims = self._get_mc_sims(street)
            win_rate = monte_carlo_win_rate(my_hand, board, num_sims, opp_info)

        # ─── Redraw decision ─────────────────────────────────────────
        if RedrawAction in legal_actions and not self.used_redraw:
            should_redraw, target_type, target_idx, improvement = \
                self._evaluate_redraw_options(round_state, active)

            if should_redraw:
                self.used_redraw = True
                # Combine redraw with a betting action
                inner_action = self._get_betting_action(
                    round_state, active, legal_actions - {RedrawAction},
                    win_rate + improvement, continue_cost, pot, my_stack
                )
                return RedrawAction(target_type, target_idx, inner_action)

        # ─── Betting action ──────────────────────────────────────────
        return self._get_betting_action(
            round_state, active, legal_actions,
            win_rate, continue_cost, pot, my_stack
        )

    def _get_betting_action(self, round_state, active, legal_actions, win_rate,
                             continue_cost, pot, my_stack):
        """Core betting logic based on win rate and pot odds."""
        street = round_state.street

        # Pot odds calculation
        if continue_cost > 0:
            pot_odds = continue_cost / (pot + continue_cost)
        else:
            pot_odds = 0.0

        # ─── PREFLOP STRATEGY ────────────────────────────────────────
        if street == 0:
            return self._preflop_action(round_state, active, legal_actions,
                                        win_rate, continue_cost, pot)

        # ─── POST-FLOP STRATEGY ──────────────────────────────────────

        # FOLD: when hand is too weak relative to the cost
        if continue_cost > 0 and win_rate < pot_odds * 0.85:
            # Also consider implied odds / bluff catching
            if win_rate < 0.25 or continue_cost > my_stack * 0.3:
                if FoldAction in legal_actions:
                    return FoldAction()

        # CHECK: when we can check and hand is marginal
        if continue_cost == 0 and CheckAction in legal_actions:
            # With weak hands, check
            if win_rate < 0.40:
                # Occasionally check-raise bluff against aggressive opponents
                if (self.opp_model.is_aggressive() and
                    win_rate > 0.30 and random.random() < 0.08):
                    pass  # Fall through to raise logic
                else:
                    return CheckAction()

            # Medium hands — mix between check and bet
            if win_rate < 0.55:
                if random.random() < 0.55:  # Check more often with medium hands
                    return CheckAction()
                # Fall through to raise

        # RAISE / BET: with strong hands or as bluff
        if RaiseAction in legal_actions:
            should_raise = False

            if win_rate > 0.60:
                # Value raise
                should_raise = True
            elif win_rate > 0.50 and continue_cost == 0:
                # Continuation bet / probe with decent hands
                should_raise = random.random() < 0.60
            elif win_rate > 0.35 and self.opp_model.folds_to_pressure():
                # Semi-bluff against foldy opponents
                should_raise = random.random() < 0.35
            elif win_rate < 0.25 and continue_cost == 0 and random.random() < 0.12:
                # Pure bluff (rare)
                should_raise = True

            if should_raise:
                amount = self._bet_sizing(round_state, active, win_rate)
                return RaiseAction(amount)

        # CALL: when pot odds justify it
        if CallAction in legal_actions:
            if win_rate >= pot_odds * 0.9:
                return CallAction()
            # Call small bets with drawing hands
            if continue_cost <= 10 and win_rate > 0.30:
                return CallAction()
            # Adjust for opponent tendencies
            if self.opp_model.is_aggressive() and win_rate > pot_odds * 0.7:
                # Call down aggressive opponents more
                return CallAction()

        # DEFAULT: check if possible, fold otherwise
        if CheckAction in legal_actions:
            return CheckAction()
        if CallAction in legal_actions and continue_cost <= 5:
            return CallAction()
        return FoldAction()

    def _preflop_action(self, round_state, active, legal_actions,
                         hand_strength, continue_cost, pot):
        """Preflop-specific strategy."""
        min_raise, max_raise = round_state.raise_bounds() if RaiseAction in legal_actions else (0, 0)

        # Premium hands (top 15%) — raise/3-bet
        if hand_strength > 0.82:
            if RaiseAction in legal_actions:
                if hand_strength > 0.92:
                    # Monster: raise big
                    amount = min(max_raise, max(min_raise, int(pot * 3)))
                else:
                    # Strong: standard raise
                    amount = min(max_raise, max(min_raise, int(pot * 2.5)))
                return RaiseAction(amount)
            if CallAction in legal_actions:
                return CallAction()

        # Playable hands (top 40%)
        if hand_strength > 0.55:
            if continue_cost <= 10:
                if CallAction in legal_actions:
                    return CallAction()
                if CheckAction in legal_actions:
                    return CheckAction()
            elif continue_cost <= 25:
                if hand_strength > 0.65:
                    if CallAction in legal_actions:
                        return CallAction()
                elif self.opp_model.is_loose() and CallAction in legal_actions:
                    return CallAction()
            else:
                if hand_strength > 0.75 and CallAction in legal_actions:
                    return CallAction()

            if RaiseAction in legal_actions and continue_cost == 0:
                # Open raise with decent hands
                amount = min(max_raise, max(min_raise, int(pot * 2)))
                return RaiseAction(amount)

        # Speculative hands (suited connectors, small pairs)
        if hand_strength > 0.40:
            if continue_cost <= 5:
                if CallAction in legal_actions:
                    return CallAction()
                if CheckAction in legal_actions:
                    return CheckAction()
            if CheckAction in legal_actions:
                return CheckAction()

        # Junk hands
        if CheckAction in legal_actions:
            return CheckAction()
        if continue_cost <= 3 and CallAction in legal_actions:
            return CallAction()  # Limp with cheap blinds in position
        if FoldAction in legal_actions:
            return FoldAction()
        return CheckAction()


if __name__ == '__main__':
    run_bot(Player(), parse_args())
