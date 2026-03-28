'''
Base class for the pokerbot. Extended with on_opponent_redraw callback.
'''


class Bot():
    '''
    The base class for a pokerbot.
    '''

    def handle_new_round(self, game_state, round_state, active):
        raise NotImplementedError('handle_new_round')

    def handle_round_over(self, game_state, terminal_state, active):
        raise NotImplementedError('handle_round_over')

    def get_action(self, game_state, round_state, active):
        raise NotImplementedError('get_action')

    def on_opponent_redraw(self, target_type, target_index, old_card):
        '''
        Called by the runner when the opponent performs a redraw.
        target_type: 'hole' or 'board'
        target_index: int index of the redrawn card
        old_card: string representation of the discarded card (e.g. 'As')
        '''
        pass
