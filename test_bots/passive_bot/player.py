import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "..", "SaptiBot"))

from skeleton.actions import CallAction, CheckAction, FoldAction
from skeleton.bot import Bot
from skeleton.runner import parse_args, run_bot

class Player(Bot):
    def handle_new_round(self, game_state, round_state, active):
        pass
    def handle_round_over(self, game_state, terminal_state, active):
        pass
    def get_action(self, game_state, round_state, active):
        legal_actions = round_state.legal_actions()
        my_pip = round_state.pips[active]
        opp_pip = round_state.pips[1 - active]
        continue_cost = opp_pip - my_pip
        
        if CheckAction in legal_actions:
            return CheckAction()
        if continue_cost <= 10 and CallAction in legal_actions:
            return CallAction()
        return FoldAction()

if __name__ == "__main__":
    run_bot(Player(), parse_args())
