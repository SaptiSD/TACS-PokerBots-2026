import os
import sys
import random

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "..", "python_skeleton"))

from skeleton.actions import CallAction, CheckAction, FoldAction, RedrawAction
from skeleton.bot import Bot
from skeleton.runner import parse_args, run_bot

class Player(Bot):
    def handle_new_round(self, game_state, round_state, active):
        pass
    def handle_round_over(self, game_state, terminal_state, active):
        pass
    def get_action(self, game_state, round_state, active):
        legal_actions = round_state.legal_actions()
        
        action = None
        if CallAction in legal_actions:
            action = CallAction()
        elif CheckAction in legal_actions:
            action = CheckAction()
        else:
            action = FoldAction()

        # Randomly redraw on flop to see if they get lucky
        if RedrawAction in legal_actions and round_state.street == 3:
            if random.random() < 0.25:
                return RedrawAction("hole", random.randint(0, 1), action)
                
        return action

if __name__ == "__main__":
    run_bot(Player(), parse_args())
