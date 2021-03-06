import random
import string
import collections

import action


class RandomBot:
    def __init__(self):
        self.prev_act = None

    def choose_action(self, state):
        if state['message']['is_more']:
            act = action.Action.MORE
        elif state['message']['is_yn']:
            act = (action.Action.NO if 'Beware' in state['message']['text']
                   else action.Action.YES)
        else:
            act = random.choice([act for act in action.Action
                                 if act in action.MOVE_ACTIONS])
        self.prev_act = act
        return act

    def get_status(self):
        train_string = 'TRAIN' if self.train else 'TEST'
        status = '{}\tEPOCH:{}'.format(train_string, self.epoch)
        if self.prev_act is not None:
            status += '\t{}'.format(self.prev_act)
        return status


class QLearningBot:
    PATTERNS = [string.ascii_letters, '+', '>', '-', '|', ' ', '#']

    def __init__(self, lr=0.2, epsilon=0.1, discount=0.6):
        self.prev_state = None
        self.prev_act = None
        self.prev_reward = None
        self.prev_map = None
        self.prev_poses = []
        self.prev_level = None
        self.prev_Q = None
        self.beneath = None
        self.prev_discovered = False
        self.lr = lr
        self.epsilon = epsilon
        self.discount = discount
        self.state_act_counts = collections.defaultdict(int)
        self.Q = collections.defaultdict(float)

    def find_self(self, state_map):
        for y in range(len(state_map)):
            for x in range(len(state_map[0])):
                if state_map[y][x] == '@':
                    return x, y
        return None

    def get_neighbors(self, state_map, x, y):
        neighbors = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if dx == dy == 0:
                    continue
                try:
                    neighbors.append(state_map[y + dy][x + dx])
                except IndexError:
                    neighbors.append(' ')
        return neighbors

    def update_prev_map(self, new_map):
        replaced_map = self.prev_map
        self.prev_map = new_map
        for line, row in enumerate(self.prev_map):
            if '@' in row:
                if replaced_map is None:
                    beneath = '.'
                else:
                    beneath = replaced_map[line][row.index('@')]
                self.prev_map[line] = row.replace('@', beneath)
                break
        if replaced_map != self.prev_map:
            self.prev_discovered = True

    def parse_state(self, state):
        pos = self.find_self(state['map'])
        if pos is None or self.prev_map is None:
            parsed = None
        else:
            parsed = []
            x, y = pos
            self.beneath = self.prev_map[y][x]
            neighbors = self.get_neighbors(state['map'], x, y)
            for pattern in self.PATTERNS:
                for neighbor in neighbors:
                    parsed.append(neighbor in pattern)
                parsed.append(self.beneath in pattern)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    parsed.append((x + dx, y + dy) in self.prev_poses)

        self.update_prev_map(state['map'])
        if parsed is None:
            return None
        binary_rep = ''.join(['1' if part else '0' for part in parsed])
        return int(binary_rep, 2)

    def update_Q(self, parsed_state):
        state_act_pair = (self.prev_state, self.prev_act)
        self.state_act_counts[state_act_pair] += 1
        state_act_lr = self.lr # / float(self.state_act_counts[state_act_pair])
        if self.prev_state is not None:
            self.prev_Q = self.Q[state_act_pair]
            max_Q = max([self.Q[(parsed_state, act)]
                         for act in action.MOVE_ACTIONS])
            new_Q = (1 - state_act_lr) * self.prev_Q
            new_Q += state_act_lr * (self.prev_reward + self.discount * max_Q)
            self.Q[state_act_pair] = new_Q

    def modify_reward(self, reward, pos, level):
        if pos in self.prev_poses:
            reward -= 0.5
        if self.prev_discovered:
            reward += 5
            self.prev_discovered = False
        if self.prev_level is not None and level is not None:
            reward += 50 * (level - self.prev_level)
        return reward - 0.1

    def choose_action(self, state):
        pos = self.find_self(state['map'])
        parsed_state = self.parse_state(state)
        self.update_Q(parsed_state)

        if state['message']['is_more']:
            act = action.Action.MORE
        elif state['message']['is_yn']:
            act = (action.Action.NO if 'Beware' in state['message']['text']
                   else action.Action.YES)

        else:
            if random.random() < self.epsilon:
                act = random.choice(action.MOVE_ACTIONS)
            else:
                best_actions = None
                best_Q = None
                for new_act in action.MOVE_ACTIONS:
                    new_Q = self.Q[(parsed_state, new_act)]
                    if best_Q is None or new_Q > best_Q:
                        best_actions = [new_act]
                        best_Q = new_Q
                    elif new_Q == best_Q:
                        best_actions.append(new_act)
                act = random.choice(best_actions)
        self.prev_state = parsed_state
        self.prev_act = act
        level = state['Dlvl'] if 'Dlvl' in state else None
        self.prev_reward = self.modify_reward(state['reward'], pos, level)
        self.prev_poses.append(pos)
        self.prev_level = level
        return act

    def get_status(self):
        train_string = 'TRAIN' if self.train else 'TEST'
        status = '{}\tEP:{}'.format(train_string, self.epoch)
        if self.prev_state is not None and self.prev_Q is not None:
            status += '\tQ:{:.3f}\tR:{:.3f}\n\tST:{:018x}'.format(
                self.Q[(self.prev_state, self.prev_act.name)],
                self.prev_reward, self.prev_state)
        status += '\n'
        if self.beneath is not None:
            status += '\tBN:{}'.format(self.beneath)
        if self.prev_act is not None:
            status += '\t{}'.format(self.prev_act)
        status += '\n'
        for act in action.MOVE_ACTIONS:
            status += '\n\t{}:{:.3f}'.format(act.name, self.Q[(self.prev_state, act)])
        return status


class ApproxQLearningBot(QLearningBot):
    def __init__(self, lr=0.2, epsilon=0.1, discount=0.6):
        self.theta = [0 for _ in range((len(self.PATTERNS) + 1)
                                       * 9 * len(action.MOVE_ACTIONS) + 1)]
        self.prev_state = None
        self.prev_act = None
        self.prev_reward = None
        self.prev_map = None
        self.prev_poses = []
        self.prev_level = None
        self.prev_Q = None
        self.beneath = None
        self.prev_discovered = False
        self.lr = lr
        self.epsilon = epsilon
        self.discount = discount

    def update_Q(self, parsed_state):
        if self.prev_state is not None:
            self.prev_Q = self.calc_Q(self.prev_state, self.prev_act)
            max_Q = max([self.calc_Q(parsed_state, act)
                         for act in action.MOVE_ACTIONS])
            update = self.lr * (self.prev_reward + self.discount * max_Q - self.prev_Q)
            binary_state = self.get_binary_state(self.prev_state, self.prev_act)
            change = [0 for _ in self.theta]
            for i in range(len(self.theta)):
                change[i] += update * binary_state[i]
                self.theta[i] += update * binary_state[i]

    def get_binary_state(self, parsed_state, act):
        state_values = [int(value) for value in '{:072b}'.format(parsed_state)]
        binary_state = []
        for new_act in action.MOVE_ACTIONS:
            if new_act == act:
                binary_state.extend(state_values)
            else:
                binary_state.extend([0 for _ in state_values])
        binary_state.append(1)
        # from tqdm import tqdm; tqdm.write(', '.join([str(value) for value in binary_state]))
        # from tqdm import tqdm; tqdm.write(', '.join([str(value) for value in state_values]))
        # import time; time.sleep(5)


        return binary_state

    def calc_Q(self, parsed_state, act):
        binary_state = self.get_binary_state(parsed_state, act)
        return sum([param * value for param, value in zip(
            self.theta, binary_state)])

    def choose_action(self, state):
        pos = self.find_self(state['map'])
        parsed_state = self.parse_state(state)
        if parsed_state is not None:
            self.update_Q(parsed_state)

        if state['message']['is_more']:
            act = action.Action.MORE
        elif state['message']['is_yn']:
            act = (action.Action.NO if 'Beware' in state['message']['text']
                   else action.Action.YES)

        else:
            if random.random() < self.epsilon or parsed_state is None:
                act = random.choice(action.MOVE_ACTIONS)
            else:
                best_actions = None
                best_Q = None
                for new_act in action.MOVE_ACTIONS:
                    new_Q = self.calc_Q(parsed_state, new_act)
                    if best_Q is None or new_Q > best_Q:
                        best_actions = [new_act]
                        best_Q = new_Q
                    elif new_Q == best_Q:
                        best_actions.append(new_act)
                act = random.choice(best_actions)
        self.prev_state = parsed_state
        self.prev_act = act
        level = state['Dlvl'] if 'Dlvl' in state else None
        self.prev_reward = self.modify_reward(state['reward'], pos, level)
        self.prev_poses.append(pos)
        self.prev_level = level
        return act

    def get_status(self):
        train_string = 'TRAIN' if self.train else 'TEST'
        status = '{}\tEP:{}'.format(train_string, self.epoch)
        if self.prev_state is not None and self.prev_Q is not None:
            status += '\tQ:{:.3f}\tR:{:.3f}\n\tST:{:018x}'.format(
                self.calc_Q(self.prev_state, self.prev_act),
                self.prev_reward, self.prev_state)
        status += '\n'
        if self.beneath is not None:
            status += '\tBN:{}'.format(self.beneath)
        if self.prev_act is not None:
            status += '\t{}'.format(self.prev_act)
        status += '\n'
        if self.prev_state is not None:
            for act in action.MOVE_ACTIONS:
                status += '\n\t{}:{:.3f}'.format(act.name, self.calc_Q(self.prev_state, act))
        status += '\n'
        status += '(' + ','.join(['{:.1f}'.format(digit) for digit in self.theta]) + ')'
        return status



class ScheduledQLearningBot(QLearningBot):
    def __init__(self, lr=0.2, delta_epsilon=0.2, every=10, discount=0.6):
        self.prev_state = None
        self.prev_act = None
        self.prev_reward = None
        self.prev_map = None
        self.prev_poses = []
        self.prev_level = None
        self.prev_Q = None
        self.beneath = None
        self.prev_discovered = False
        self.lr = lr
        self.epsilon = 1.0
        self.delta_epsilon = delta_epsilon
        self.every = every
        self.discount = discount
        self.state_act_counts = collections.defaultdict(int)
        self.Q = collections.defaultdict(float)

    def choose_action(self, state):
        self.epsilon = 1 - int(self.epoch / self.every) * self.delta_epsilon
        pos = self.find_self(state['map'])
        parsed_state = self.parse_state(state)
        self.update_Q(parsed_state)

        if state['message']['is_more']:
            act = action.Action.MORE
        elif state['message']['is_yn']:
            act = (action.Action.NO if 'Beware' in state['message']['text']
                   else action.Action.YES)

        else:
            if random.random() < self.epsilon:
                act = random.choice(action.MOVE_ACTIONS)
            else:
                best_actions = None
                best_Q = None
                for new_act in action.MOVE_ACTIONS:
                    new_Q = self.Q[(parsed_state, new_act)]
                    if best_Q is None or new_Q > best_Q:
                        best_actions = [new_act]
                        best_Q = new_Q
                    elif new_Q == best_Q:
                        best_actions.append(new_act)
                act = random.choice(best_actions)
        self.prev_state = parsed_state
        self.prev_act = act
        level = state['Dlvl'] if 'Dlvl' in state else None
        self.prev_reward = self.modify_reward(state['reward'], pos, level)
        self.prev_poses.append(pos)
        self.prev_level = level
        return act


class ScheduledApproxQLearningBot(ApproxQLearningBot):
    def __init__(self, lr=0.2, delta_epsilon=0.1, every=10, discount=0.6):
        self.theta = [0 for _ in range((len(self.PATTERNS) + 1)
                                       * 9 * len(action.MOVE_ACTIONS) + 1)]
        self.prev_state = None
        self.prev_act = None
        self.prev_reward = None
        self.prev_map = None
        self.prev_poses = []
        self.prev_level = None
        self.prev_Q = None
        self.beneath = None
        self.prev_discovered = False
        self.lr = lr
        self.epsilon = 1
        self.delta_epsilon = delta_epsilon
        self.every = every
        self.discount = discount

    def choose_action(self, state):
        self.epsilon = 1 - int(self.epoch / self.every) * self.delta_epsilon
        pos = self.find_self(state['map'])
        parsed_state = self.parse_state(state)
        if parsed_state is not None:
            self.update_Q(parsed_state)

        if state['message']['is_more']:
            act = action.Action.MORE
        elif state['message']['is_yn']:
            act = (action.Action.NO if 'Beware' in state['message']['text']
                   else action.Action.YES)

        else:
            if random.random() < self.epsilon or parsed_state is None:
                act = random.choice(action.MOVE_ACTIONS)
            else:
                best_actions = None
                best_Q = None
                for new_act in action.MOVE_ACTIONS:
                    new_Q = self.calc_Q(parsed_state, new_act)
                    if best_Q is None or new_Q > best_Q:
                        best_actions = [new_act]
                        best_Q = new_Q
                    elif new_Q == best_Q:
                        best_actions.append(new_act)
                act = random.choice(best_actions)
        self.prev_state = parsed_state
        self.prev_act = act
        level = state['Dlvl'] if 'Dlvl' in state else None
        self.prev_reward = self.modify_reward(state['reward'], pos, level)
        self.prev_poses.append(pos)
        self.prev_level = level
        return act


