'''
tight_bot: Tight-passive (rock) poker bot.

Preflop hand rankings using RANKS = '23456789TJQKA':
  PREMIUM (raise max): AA, KK, QQ, JJ, TT, AKs, AQs, AKo
  STRONG  (raise min): 99, 88, AJs, AQo, KQs
  FOLD everything else to any raise. Check/fold if no raise.

Postflop:
  - Only continue with top pair or better. Fold to any bet without strong hand.
  - Never bluff.

Redraw:
  - Only if dealt a non-premium/non-strong hand that somehow reached action
    (equity < 0.35), replace the lower card.
  - Never redraw in premium/strong situations.
'''
from skeleton.actions import FoldAction, CallAction, CheckAction, RaiseAction, RedrawAction
from skeleton.states import STARTING_STACK, BIG_BLIND
from skeleton.bot import Bot
from skeleton.runner import parse_args, run_bot


RANKS = '23456789TJQKA'


class Player(Bot):
    '''
    A tight-passive (rock) pokerbot.
    '''

    def __init__(self):
        self.hand_class = 'fold'  # reset each round

    def handle_new_round(self, game_state, round_state, active):
        self.hand_class = 'fold'

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
    # Preflop classification
    # ------------------------------------------------------------------

    def _classify_preflop(self, my_cards):
        '''
        Returns "premium", "strong", or "fold".
        Uses RANKS = '23456789TJQKA'.
        '''
        c0, c1 = my_cards[0], my_cards[1]
        r0, r1 = self._rank_val(c0), self._rank_val(c1)
        s0, s1 = self._suit(c0), self._suit(c1)

        if r0 < 0 or r1 < 0:
            return 'fold'

        hi = max(r0, r1)
        lo = min(r0, r1)
        suited = (s0 == s1)
        is_pair = (r0 == r1)

        rank_A = RANKS.index('A')  # 12
        rank_K = RANKS.index('K')  # 11
        rank_Q = RANKS.index('Q')  # 10
        rank_J = RANKS.index('J')  # 9
        rank_T = RANKS.index('T')  # 8
        rank_9 = RANKS.index('9')  # 7
        rank_8 = RANKS.index('8')  # 6

        # PREMIUM: AA, KK, QQ, JJ, TT (pairs >= TT), AKs, AQs, AKo
        if is_pair and hi >= rank_T:
            return 'premium'
        if hi == rank_A and lo == rank_K:
            # AKs or AKo -> both premium
            return 'premium'
        if hi == rank_A and lo == rank_Q and suited:
            return 'premium'

        # STRONG: 99, 88, AJs, AQo, KQs
        if is_pair and hi in (rank_9, rank_8):
            return 'strong'
        if hi == rank_A and lo == rank_J and suited:
            return 'strong'
        if hi == rank_A and lo == rank_Q and not suited:
            return 'strong'
        if hi == rank_K and lo == rank_Q and suited:
            return 'strong'

        return 'fold'

    # ------------------------------------------------------------------
    # Postflop hand strength
    # ------------------------------------------------------------------

    def _has_top_pair_or_better(self, my_cards, board):
        '''
        Returns True if hole cards make top pair (pair with the highest board card) or better.
        Also True for pocket pairs that are an overpair to the board, or trips/better.
        '''
        if not board:
            return False

        hole_ranks = [self._rank_val(c) for c in my_cards if c and c != '??']
        board_ranks = [self._rank_val(c) for c in board if c and c != '??']

        if not board_ranks:
            return False

        top_board_rank = max(board_ranks)

        # Pocket overpair: both hole cards same rank, higher than all board cards
        if len(hole_ranks) == 2 and hole_ranks[0] == hole_ranks[1]:
            if hole_ranks[0] > top_board_rank:
                return True

        # Check for pair with top board card
        for hr in hole_ranks:
            if hr == top_board_rank:
                return True

        # Check for trips or better: one hole card matches two board cards
        for hr in hole_ranks:
            if board_ranks.count(hr) >= 2:
                return True

        # Two pair or better: two hole cards each pair with different board cards
        paired_count = sum(1 for hr in hole_ranks if hr in board_ranks)
        if paired_count >= 2:
            return True

        return False

    # ------------------------------------------------------------------
    # Redraw logic
    # ------------------------------------------------------------------

    def _should_redraw(self, round_state, active):
        '''Only redraw if hand class is "fold" and redraw is available.'''
        if round_state.redraws_used[active]:
            return False
        if round_state.street >= 5:
            return False
        # Only redraw on marginal hands (fold classification)
        return self.hand_class == 'fold'

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

        # Classify preflop hand (update self.hand_class on preflop)
        if street == 0:
            self.hand_class = self._classify_preflop(my_cards)

        # --- Redraw (only for non-premium/strong, i.e. fold-classified hands) ---
        if RedrawAction in legal_actions and self._should_redraw(round_state, active):
            target_index = self._weakest_hole_index(my_cards)
            # After redraw, play passively (check or fold)
            if CheckAction in legal_actions:
                return RedrawAction('hole', target_index, CheckAction())
            if CallAction in legal_actions and continue_cost <= BIG_BLIND * 2:
                return RedrawAction('hole', target_index, CallAction())
            return RedrawAction('hole', target_index, FoldAction())

        # --- Preflop ---
        if street == 0:
            if self.hand_class == 'premium':
                if RaiseAction in legal_actions:
                    _, max_raise = round_state.raise_bounds()
                    return RaiseAction(max_raise)
                if CallAction in legal_actions:
                    return CallAction()
                return CheckAction()

            if self.hand_class == 'strong':
                if RaiseAction in legal_actions and continue_cost == 0:
                    min_raise, _ = round_state.raise_bounds()
                    return RaiseAction(min_raise)
                if CallAction in legal_actions and continue_cost <= BIG_BLIND * 4:
                    return CallAction()
                if CheckAction in legal_actions:
                    return CheckAction()
                return FoldAction()

            # 'fold': fold to any raise, check otherwise
            if continue_cost > 0:
                return FoldAction()
            return CheckAction() if CheckAction in legal_actions else FoldAction()

        # --- Postflop (only continue with top pair or better) ---
        has_strong_hand = self._has_top_pair_or_better(my_cards, board)

        if has_strong_hand:
            # Tight: don't bluff but do value bet minimally
            if continue_cost > 0:
                if CallAction in legal_actions:
                    return CallAction()
                return FoldAction()
            # Check when no bet to call (never bluff)
            return CheckAction() if CheckAction in legal_actions else FoldAction()

        # No strong hand: fold to any bet, check otherwise
        if continue_cost > 0:
            return FoldAction()
        return CheckAction() if CheckAction in legal_actions else FoldAction()


if __name__ == '__main__':
    run_bot(Player(), parse_args())
