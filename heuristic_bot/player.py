'''
heuristic_bot: Rule-based poker bot with no Monte Carlo simulation.

Preflop hand classification:
  - "premium": pocket pair >= TT, AKs, AKo, AQs  -> raise big (3x BB)
  - "strong":  pocket pair 77-99, AJs, AJo, AQo, KQs -> raise small (min raise)
  - "playable": suited connectors, any pocket pair < 77, broadway offsuit -> call/check
  - "weak":    everything else -> fold to raises, check otherwise

Postflop:
  - Count outs for flush/straight draws.
  - Equity ~ outs * 4% on flop, outs * 2% on turn.
  - Bet/call if equity >= 40%, call/check if 25-40%, fold to bets if < 25%.

Redraw:
  - Preflop: redraw if hand is "weak".
  - Postflop: redraw if equity < 25% and redraw not yet used.
  - Always replace the weakest hole card.
'''
from skeleton.actions import FoldAction, CallAction, CheckAction, RaiseAction, RedrawAction
from skeleton.states import STARTING_STACK, BIG_BLIND
from skeleton.bot import Bot
from skeleton.runner import parse_args, run_bot


RANKS = '23456789TJQKA'
SUITS = 'hdsc'


class Player(Bot):
    '''
    A rule-based heuristic pokerbot with no Monte Carlo.
    '''

    def __init__(self):
        pass

    def handle_new_round(self, game_state, round_state, active):
        pass

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
        Returns one of: "premium", "strong", "playable", "weak".
        '''
        c0, c1 = my_cards[0], my_cards[1]
        r0, r1 = self._rank_val(c0), self._rank_val(c1)
        s0, s1 = self._suit(c0), self._suit(c1)

        if r0 < 0 or r1 < 0:
            return 'weak'

        # Sort so hi >= lo
        hi = max(r0, r1)
        lo = min(r0, r1)
        suited = (s0 == s1)
        is_pair = (r0 == r1)

        rank_T = RANKS.index('T')
        rank_9 = RANKS.index('9')
        rank_8 = RANKS.index('8')  # index 6
        rank_7 = RANKS.index('7')
        rank_A = RANKS.index('A')
        rank_K = RANKS.index('K')
        rank_Q = RANKS.index('Q')
        rank_J = RANKS.index('J')

        # PREMIUM: pocket pair TT+, AKs, AKo, AQs
        if is_pair and hi >= rank_T:
            return 'premium'
        if hi == rank_A and lo == rank_K:
            return 'premium'
        if hi == rank_A and lo == rank_Q and suited:
            return 'premium'

        # STRONG: pocket pair 77-99, AJs, AJo, AQo, KQs
        if is_pair and rank_7 <= hi <= rank_9:
            return 'strong'
        if hi == rank_A and lo == rank_J:
            return 'strong'
        if hi == rank_A and lo == rank_Q and not suited:
            return 'strong'
        if hi == rank_K and lo == rank_Q and suited:
            return 'strong'

        # PLAYABLE: any pair, suited connectors (gap <= 1), broadway offsuit (both >= T)
        if is_pair:
            return 'playable'
        if suited and (hi - lo) <= 2:
            return 'playable'
        if hi >= rank_T and lo >= rank_T:
            return 'playable'

        return 'weak'

    # ------------------------------------------------------------------
    # Postflop equity estimation via outs
    # ------------------------------------------------------------------

    def _count_outs(self, my_cards, board):
        '''
        Estimates outs for flush draw or open-ended straight draw.
        Returns integer number of outs.
        '''
        all_cards = [c for c in (list(my_cards) + list(board)) if c and c != '??']
        outs = 0

        # Flush draw: 4 cards of same suit -> 9 outs
        suit_counts = {}
        for c in all_cards:
            s = self._suit(c)
            if s:
                suit_counts[s] = suit_counts.get(s, 0) + 1
        if any(v == 4 for v in suit_counts.values()):
            outs = max(outs, 9)

        # Straight draw: look at unique sorted rank values
        rank_vals = sorted(set(self._rank_val(c) for c in all_cards if self._rank_val(c) >= 0))
        # Check for 4 consecutive ranks (open-ended) -> 8 outs
        # Check for 4 ranks with one gap (gutshot) -> 4 outs
        for i in range(len(rank_vals)):
            window_oesd = [r for r in rank_vals if rank_vals[i] <= r <= rank_vals[i] + 4]
            if len(window_oesd) >= 4:
                consecutive = sum(1 for j in range(len(window_oesd) - 1)
                                  if window_oesd[j + 1] - window_oesd[j] == 1)
                if consecutive >= 3:
                    outs = max(outs, 8)
                elif consecutive >= 2:
                    outs = max(outs, 4)

        return outs

    def _has_made_hand(self, my_cards, board):
        '''Returns True if we have at least a pair using hole cards + board.'''
        if not board:
            return False
        hole_ranks = [self._rank_val(c) for c in my_cards if c and c != '??']
        board_ranks = [self._rank_val(c) for c in board if c and c != '??']
        # Pair using hole cards with board
        for hr in hole_ranks:
            if hr in board_ranks:
                return True
        # Pocket pair
        if len(hole_ranks) == 2 and hole_ranks[0] == hole_ranks[1]:
            return True
        # Pair on board (irrelevant for our hand strength but counts for made hand)
        for i in range(len(board_ranks)):
            for j in range(i + 1, len(board_ranks)):
                if board_ranks[i] == board_ranks[j]:
                    return True
        return False

    def _postflop_equity(self, my_cards, board, street):
        '''
        Estimate equity from outs.
        Flop (street=3): equity ~ outs * 4%
        Turn (street=4): equity ~ outs * 2%
        Also add baseline if we have a made hand.
        '''
        if self._has_made_hand(my_cards, board):
            return 0.55  # decent made hand baseline

        outs = self._count_outs(my_cards, board)
        if street == 3:
            return min(outs * 0.04, 0.85)
        if street == 4:
            return min(outs * 0.02, 0.85)
        return 0.0

    # ------------------------------------------------------------------
    # Redraw logic
    # ------------------------------------------------------------------

    def _should_redraw(self, round_state, active, hand_class, equity):
        if round_state.redraws_used[active]:
            return False
        if round_state.street >= 5:
            return False
        # Preflop: redraw if weak
        if round_state.street == 0 and hand_class == 'weak':
            return True
        # Postflop: redraw if equity below threshold
        if round_state.street in (3, 4) and equity < 0.25:
            return True
        return False

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

        hand_class = self._classify_preflop(my_cards)

        # Compute postflop equity if we're past preflop
        if street == 0:
            equity = {'premium': 0.75, 'strong': 0.60, 'playable': 0.50, 'weak': 0.30}[hand_class]
        else:
            equity = self._postflop_equity(my_cards, board, street)

        # Check redraw condition
        if RedrawAction in legal_actions and self._should_redraw(round_state, active, hand_class, equity):
            target_index = self._weakest_hole_index(my_cards)
            if RaiseAction in legal_actions and equity >= 0.40:
                min_raise, _ = round_state.raise_bounds()
                return RedrawAction('hole', target_index, RaiseAction(min_raise))
            if CheckAction in legal_actions:
                return RedrawAction('hole', target_index, CheckAction())
            if CallAction in legal_actions and continue_cost <= pot * 0.3:
                return RedrawAction('hole', target_index, CallAction())
            if FoldAction in legal_actions and continue_cost > 0:
                return RedrawAction('hole', target_index, FoldAction())
            if CheckAction in legal_actions:
                return RedrawAction('hole', target_index, CheckAction())

        # Preflop strategy
        if street == 0:
            if hand_class == 'premium':
                if RaiseAction in legal_actions:
                    min_raise, max_raise = round_state.raise_bounds()
                    # Raise to 3x BB or more
                    target = max(min_raise, BIG_BLIND * 3)
                    target = min(target, max_raise)
                    return RaiseAction(target)
                return CallAction() if CallAction in legal_actions else CheckAction()

            if hand_class == 'strong':
                if RaiseAction in legal_actions and continue_cost == 0:
                    min_raise, _ = round_state.raise_bounds()
                    return RaiseAction(min_raise)
                if CallAction in legal_actions and continue_cost <= BIG_BLIND * 4:
                    return CallAction()
                if CheckAction in legal_actions:
                    return CheckAction()
                return FoldAction()

            if hand_class == 'playable':
                if continue_cost == 0:
                    return CheckAction() if CheckAction in legal_actions else CallAction()
                if continue_cost <= BIG_BLIND * 3 and CallAction in legal_actions:
                    return CallAction()
                return FoldAction()

            # weak
            if continue_cost > 0:
                return FoldAction()
            return CheckAction() if CheckAction in legal_actions else FoldAction()

        # Postflop strategy
        if equity >= 0.60:
            # Strong hand: raise big
            if RaiseAction in legal_actions:
                min_raise, max_raise = round_state.raise_bounds()
                target = min_raise + int((max_raise - min_raise) * 0.6)
                return RaiseAction(target)
            if CallAction in legal_actions:
                return CallAction()
            return CheckAction()

        if equity >= 0.40:
            # Good equity: call or bet small
            if continue_cost == 0 and RaiseAction in legal_actions:
                min_raise, _ = round_state.raise_bounds()
                return RaiseAction(min_raise)
            if CallAction in legal_actions and continue_cost <= pot * 0.5:
                return CallAction()
            if CheckAction in legal_actions:
                return CheckAction()
            return FoldAction()

        if equity >= 0.25:
            # Marginal: call small bets, check otherwise
            if continue_cost == 0:
                return CheckAction() if CheckAction in legal_actions else FoldAction()
            if CallAction in legal_actions and continue_cost <= pot * 0.25:
                return CallAction()
            return FoldAction()

        # Below 25% equity: fold to bets, check otherwise
        if continue_cost > 0:
            return FoldAction()
        return CheckAction() if CheckAction in legal_actions else FoldAction()


if __name__ == '__main__':
    run_bot(Player(), parse_args())
