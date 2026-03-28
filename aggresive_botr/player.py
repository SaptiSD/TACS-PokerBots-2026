'''
aggressive_bot: Loose-aggressive (LAG) poker bot.

Strategy:
  - Preflop: raise 3x BB with any hand ranked above bottom 30% (rough equity > 0.38),
    otherwise call to see a flop.
  - Postflop: continuation bet 75% of the time regardless of hand strength.
    Raise big with any pair or better.
  - River: bluff 20% of the time when checked to with no made hand.
  - Redraw: redraw preflop if both hole cards below 7, or postflop if board doesn't
    connect at all (no pair, no draw of any kind). Always pair redraw with a raise.
  - Tracks opponent fold frequency to opportunistically bluff more.
'''
import random
from skeleton.actions import FoldAction, CallAction, CheckAction, RaiseAction, RedrawAction
from skeleton.states import STARTING_STACK, BIG_BLIND
from skeleton.bot import Bot
from skeleton.runner import parse_args, run_bot


RANKS = '23456789TJQKA'


class Player(Bot):
    '''
    A loose-aggressive pokerbot.
    '''

    def __init__(self):
        self.opp_total_actions = 0
        self.opp_folds = 0
        self.hand_count = 0

    def handle_new_round(self, game_state, round_state, active):
        self.hand_count += 1

    def handle_round_over(self, game_state, terminal_state, active):
        pass

    # ------------------------------------------------------------------
    # Card utilities
    # ------------------------------------------------------------------

    def _rank_val(self, card):
        if not card or card == '??':
            return -1
        try:
            return RANKS.index(card[0])
        except ValueError:
            return -1

    def _suit(self, card):
        if not card or len(card) < 2 or card == '??':
            return None
        return card[1]

    def _weakest_hole_index(self, my_cards):
        v0 = self._rank_val(my_cards[0])
        v1 = self._rank_val(my_cards[1])
        return 0 if v0 <= v1 else 1

    # ------------------------------------------------------------------
    # Hand evaluation
    # ------------------------------------------------------------------

    def _preflop_equity(self, my_cards):
        '''
        Rough preflop equity estimate for LAG play.
        Returns a float 0.0-1.0.
        '''
        c0, c1 = my_cards[0], my_cards[1]
        r0, r1 = self._rank_val(c0), self._rank_val(c1)
        s0, s1 = self._suit(c0), self._suit(c1)

        if r0 < 0 or r1 < 0:
            return 0.30

        hi = max(r0, r1)
        lo = min(r0, r1)
        suited = (s0 == s1)
        is_pair = (r0 == r1)

        rank_A = RANKS.index('A')
        rank_K = RANKS.index('K')
        rank_T = RANKS.index('T')
        rank_7 = RANKS.index('7')

        # Base score from high card
        base = (hi / 12.0) * 0.5 + (lo / 12.0) * 0.2

        # Adjustments
        if is_pair:
            base += 0.15 + (hi / 12.0) * 0.10
        if suited:
            base += 0.04
        if (hi - lo) <= 2 and not is_pair:
            base += 0.03  # connectedness

        return min(base, 0.95)

    def _has_pair_or_better(self, my_cards, board):
        '''Returns True if hole cards make at least a pair with the board, or a pocket pair.'''
        hole_ranks = [self._rank_val(c) for c in my_cards if c and c != '??']
        board_ranks = [self._rank_val(c) for c in board if c and c != '??']

        if len(hole_ranks) == 2 and hole_ranks[0] == hole_ranks[1]:
            return True
        for hr in hole_ranks:
            if hr in board_ranks:
                return True
        return False

    def _has_any_draw(self, my_cards, board):
        '''Returns True if we have a flush draw or any straight draw (including gutshot).'''
        all_cards = [c for c in list(my_cards) + list(board) if c and c != '??']

        # Flush draw: exactly 4 of same suit
        suit_counts = {}
        for c in all_cards:
            s = self._suit(c)
            if s:
                suit_counts[s] = suit_counts.get(s, 0) + 1
        if any(v >= 4 for v in suit_counts.values()):
            return True

        # Straight draw: 4 cards within a 5-rank window
        rank_vals = sorted(set(self._rank_val(c) for c in all_cards if self._rank_val(c) >= 0))
        for i in range(len(rank_vals)):
            window = [r for r in rank_vals if rank_vals[i] <= r <= rank_vals[i] + 4]
            if len(window) >= 4:
                return True

        return False

    def _board_connects(self, my_cards, board):
        '''Returns True if we have at least a pair or a draw.'''
        if not board:
            return True  # preflop counts as connected
        return self._has_pair_or_better(my_cards, board) or self._has_any_draw(my_cards, board)

    # ------------------------------------------------------------------
    # Redraw logic
    # ------------------------------------------------------------------

    def _should_redraw(self, round_state, active):
        if round_state.redraws_used[active]:
            return False
        if round_state.street >= 5:
            return False

        my_cards = round_state.hands[active]
        board = round_state.board
        street = round_state.street

        # Preflop: both hole cards below rank 7
        if street == 0:
            r0 = self._rank_val(my_cards[0])
            r1 = self._rank_val(my_cards[1])
            rank_7 = RANKS.index('7')
            return r0 < rank_7 and r1 < rank_7

        # Postflop: board doesn't connect at all
        if street in (3, 4):
            return not self._board_connects(my_cards, board)

        return False

    # ------------------------------------------------------------------
    # Bluff frequency
    # ------------------------------------------------------------------

    def _bluff_frequency(self):
        '''
        Adjust bluff frequency upward if opponent folds often.
        Base is 20%; goes up to 40% if opponent folds > 50%.
        '''
        if self.opp_total_actions == 0:
            return 0.20
        fold_rate = self.opp_folds / self.opp_total_actions
        if fold_rate > 0.50:
            return 0.40
        if fold_rate > 0.35:
            return 0.30
        return 0.20

    # ------------------------------------------------------------------
    # Main action
    # ------------------------------------------------------------------

    def get_action(self, game_state, round_state, active):
        legal_actions = round_state.legal_actions()
        street = round_state.street
        my_cards = round_state.hands[active]
        board = round_state.board
        my_pip = round_state.pips[active]
        opp_pip = round_state.pips[1 - active]
        continue_cost = opp_pip - my_pip
        pot = my_pip + opp_pip

        # Track opponent actions (simple: if there was a cost to call, opp bet/raised)
        if continue_cost == 0:
            self.opp_total_actions += 1
        else:
            self.opp_total_actions += 1

        # --- Redraw ---
        if RedrawAction in legal_actions and self._should_redraw(round_state, active):
            target_index = self._weakest_hole_index(my_cards)
            if RaiseAction in legal_actions:
                min_raise, max_raise = round_state.raise_bounds()
                # Raise to 3x BB or pot-size
                target = min_raise + int((max_raise - min_raise) * 0.5)
                return RedrawAction('hole', target_index, RaiseAction(target))
            if CallAction in legal_actions:
                return RedrawAction('hole', target_index, CallAction())
            return RedrawAction('hole', target_index, CheckAction())

        # --- Preflop ---
        if street == 0:
            equity = self._preflop_equity(my_cards)
            if equity > 0.38:
                # Raise 3x BB
                if RaiseAction in legal_actions:
                    min_raise, max_raise = round_state.raise_bounds()
                    target = max(min_raise, my_pip + BIG_BLIND * 3)
                    target = min(target, max_raise)
                    return RaiseAction(target)
                if CallAction in legal_actions:
                    return CallAction()
                return CheckAction()
            else:
                # Call to see a flop, don't fold cheaply
                if continue_cost == 0:
                    return CheckAction() if CheckAction in legal_actions else CallAction()
                if CallAction in legal_actions and continue_cost <= BIG_BLIND * 5:
                    return CallAction()
                return FoldAction()

        # --- Postflop ---
        has_hand = self._has_pair_or_better(my_cards, board)
        bluff_freq = self._bluff_frequency()

        # River bluff logic: 20% bluff when checked to with no hand
        if street == 5 and not has_hand and continue_cost == 0:
            if random.random() < bluff_freq and RaiseAction in legal_actions:
                min_raise, max_raise = round_state.raise_bounds()
                bluff_size = min_raise + int((max_raise - min_raise) * 0.4)
                return RaiseAction(bluff_size)
            return CheckAction() if CheckAction in legal_actions else FoldAction()

        # Strong hand (pair or better): raise big
        if has_hand:
            if RaiseAction in legal_actions:
                min_raise, max_raise = round_state.raise_bounds()
                target = min_raise + int((max_raise - min_raise) * 0.65)
                return RaiseAction(target)
            if CallAction in legal_actions:
                return CallAction()
            return CheckAction()

        # Continuation bet 75% of the time with no hand
        if continue_cost == 0 and RaiseAction in legal_actions:
            if random.random() < 0.75:
                min_raise, max_raise = round_state.raise_bounds()
                cbet_size = min_raise + int((max_raise - min_raise) * 0.35)
                return RaiseAction(cbet_size)
            return CheckAction()

        # Facing a bet with no hand: call if cheap, else fold
        if continue_cost > 0:
            if CallAction in legal_actions and continue_cost <= pot * 0.30:
                return CallAction()
            return FoldAction()

        return CheckAction() if CheckAction in legal_actions else FoldAction()


if __name__ == '__main__':
    run_bot(Player(), parse_args())
