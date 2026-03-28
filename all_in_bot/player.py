'''
all_in_bot: Always raises to the maximum amount.
Strategy:
  - Always tries to raise to max (all-in).
  - If can't raise, calls.
  - Folds only when forced (no call/check available).
  - Preflop: if both hole cards are below rank 8 (i.e., both are 2-7),
    uses redraw on the weaker card before going all-in.
'''
from skeleton.actions import FoldAction, CallAction, CheckAction, RaiseAction, RedrawAction
from skeleton.states import STARTING_STACK, BIG_BLIND
from skeleton.bot import Bot
from skeleton.runner import parse_args, run_bot


RANKS = '23456789TJQKA'


class Player(Bot):
    '''
    An all-in pokerbot that always raises to the maximum.
    '''

    def __init__(self):
        pass

    def handle_new_round(self, game_state, round_state, active):
        pass

    def handle_round_over(self, game_state, terminal_state, active):
        pass

    def _rank_value(self, card):
        '''Returns the numeric rank value (0-12) of a card string like "Ah", "Tc".'''
        if not card or len(card) < 1 or card == '??':
            return -1
        try:
            return RANKS.index(card[0])
        except ValueError:
            return -1

    def _weakest_hole_index(self, my_cards):
        '''Returns the index (0 or 1) of the weaker hole card.'''
        v0 = self._rank_value(my_cards[0])
        v1 = self._rank_value(my_cards[1])
        return 0 if v0 <= v1 else 1

    def _should_redraw_preflop(self, round_state, active):
        '''
        Returns True if we should redraw preflop: both hole cards are below rank 8
        (i.e., both are strictly weaker than 8, so ranks 2-7).
        Rank 8 corresponds to index 6 in RANKS ('23456789TJQKA').
        '''
        if round_state.redraws_used[active]:
            return False
        if round_state.street != 0:
            return False
        my_cards = round_state.hands[active]
        rank_8_index = RANKS.index('8')  # index 6
        v0 = self._rank_value(my_cards[0])
        v1 = self._rank_value(my_cards[1])
        # Both cards below 8 means both have rank value < rank_8_index
        return v0 < rank_8_index and v1 < rank_8_index

    def get_action(self, game_state, round_state, active):
        '''
        Always raise all-in. Redraw preflop on very weak hands before going all-in.
        '''
        legal_actions = round_state.legal_actions()

        # Preflop redraw: if both hole cards below rank 8, redraw weaker card then go all-in
        if RedrawAction in legal_actions and self._should_redraw_preflop(round_state, active):
            target_index = self._weakest_hole_index(round_state.hands[active])
            if RaiseAction in legal_actions:
                _, max_raise = round_state.raise_bounds()
                return RedrawAction('hole', target_index, RaiseAction(max_raise))
            if CallAction in legal_actions:
                return RedrawAction('hole', target_index, CallAction())
            return RedrawAction('hole', target_index, CheckAction())

        # Main strategy: always try to raise to max
        if RaiseAction in legal_actions:
            _, max_raise = round_state.raise_bounds()
            return RaiseAction(max_raise)
        if CallAction in legal_actions:
            return CallAction()
        if CheckAction in legal_actions:
            return CheckAction()
        return FoldAction()


if __name__ == '__main__':
    run_bot(Player(), parse_args())
