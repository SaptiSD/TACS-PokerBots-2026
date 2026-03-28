import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "..", "python_skeleton"))

from skeleton.actions import CallAction, CheckAction, RaiseAction, RedrawAction
from skeleton.bot import Bot
from skeleton.runner import parse_args, run_bot

class Player(Bot):
    def handle_new_round(self, game_state, round_state, active):
        pass
    def handle_round_over(self, game_state, terminal_state, active):
        pass
    def get_action(self, game_state, round_state, active):
        legal_actions = round_state.legal_actions()
        
        # Always bet/raise max
        def aggro():
            if RaiseAction in legal_actions:
                return RaiseAction(round_state.raise_bounds()[1])
            if CallAction in legal_actions:
                return CallAction()
            return CheckAction()

        # Maniac always swaps board card 0 on flop to mess with opponent
        if RedrawAction in legal_actions and round_state.street == 3:
            return RedrawAction('board', 0, aggro())
        elif RedrawAction in legal_actions and round_state.street == 4:
            return RedrawAction('board', 3, aggro())
            
        return aggro()

if __name__ == "__main__":
    run_bot(Player(), parse_args())
