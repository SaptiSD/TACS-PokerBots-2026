import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "..", "python_skeleton"))

from skeleton.actions import CallAction, CheckAction, FoldAction, RaiseAction, RedrawAction
from skeleton.bot import Bot
from skeleton.runner import parse_args, run_bot

RANKS = "23456789TJQKA"

class Player(Bot):
    def handle_new_round(self, game_state, round_state, active):
        pass
    def handle_round_over(self, game_state, terminal_state, active):
        pass
        
    def _rank_value(self, c):
        if not c or c == '??': return -1
        return RANKS.index(c[0])

    def get_action(self, game_state, round_state, active):
        legal_actions = round_state.legal_actions()
        street = round_state.street
        my_cards = round_state.hands[active]
        
        # very simple preflop filter
        if street == 0:
            r1 = self._rank_value(my_cards[0])
            r2 = self._rank_value(my_cards[1])
            is_pair = (r1 == r2 and r1 > 0)
            is_tight = (max(r1, r2) >= 10) or is_pair
            
            if not is_tight and FoldAction in legal_actions and (round_state.pips[1-active] > round_state.pips[active]):
                return FoldAction()
                
            if RaiseAction in legal_actions:
                return RaiseAction(round_state.raise_bounds()[0])
            if CallAction in legal_actions:
                return CallAction()
            return CheckAction()

        # postflop: if redraw is legal, redraw weakest card if < 8
        if RedrawAction in legal_actions and street in (3, 4):
            r1 = self._rank_value(my_cards[0])
            r2 = self._rank_value(my_cards[1])
            weak_idx = 0 if r1 <= r2 else 1
            if min(r1, r2) < 6:
                inner = RaiseAction(round_state.raise_bounds()[0]) if RaiseAction in legal_actions else (CallAction() if CallAction in legal_actions else CheckAction())
                return RedrawAction('hole', weak_idx, inner)
                
        # aggressive postflop
        if RaiseAction in legal_actions:
            return RaiseAction(round_state.raise_bounds()[0])
        elif CallAction in legal_actions:
            return CallAction()
            
        return CheckAction()

if __name__ == "__main__":
    run_bot(Player(), parse_args())
