import os

import pygame
import torch
import numpy as np
import random
from collections import deque
from snake import Snake
from main import SnakeGame
from helper import Direction
import helper
from model import Linear_QNet, QTrainer

MAX_MEMORY = 100_000
BATCH_SIZE = 256
LEARNING_RATE = 0.001
torch.device("cuda" if torch.cuda.is_available() else "cpu")


class GameState:
    def __init__(self):
        pass


class Agent:
    def __init__(self, snake_space_radius: int, model_path: str = None):
        self.total_games = 0
        self.model_path = model_path
        self.randomness = 0  # Randomness / Epsilon
        self.discount_rate = 0.9  # Discount rate / Gamma
        self.memory = deque(maxlen=MAX_MEMORY)

        # Load a model if specified, otherwise create a new one
        snake_space_diameter = (snake_space_radius * 2) + 1
        snake_space_input_size = np.power(snake_space_diameter, 2) - 1
        self.model = Linear_QNet(8 + snake_space_input_size, 512, 3)
        if model_path:
            self.model.load_state_dict(torch.load(model_path))
        self.trainer = QTrainer(self.model, LEARNING_RATE, self.discount_rate)

    def get_state(self, game: SnakeGame):
        """
        Get current State
        :param game:
        :return:
        """

        snake = game.snake
        snake_pos = snake.position.copy()

        apple_pos = snake.apple_position

        dir_left = snake.direction == Direction.LEFT
        dir_right = snake.direction == Direction.RIGHT
        dir_up = snake.direction == Direction.UP
        dir_down = snake.direction == Direction.DOWN

        def is_danger(direction: str, offset: int, body_only=False) -> bool:
            head_up, head_down, head_right, head_left = helper.offset_head(snake_pos, offset)

            if direction == "ahead":
                return (
                    (dir_up and snake.check_danger(head_up, body_only)) or
                    (dir_down and snake.check_danger(head_down, body_only)) or
                    (dir_left and snake.check_danger(head_left, body_only)) or
                    (dir_right and snake.check_danger(head_right, body_only))
                )
            elif direction == "left":
                return (
                    (dir_up and snake.check_danger(head_left, body_only)) or
                    (dir_down and snake.check_danger(head_right, body_only)) or
                    (dir_left and snake.check_danger(head_down, body_only)) or
                    (dir_right and snake.check_danger(head_up, body_only))
                )
            elif direction == "right":
                return (
                    (dir_up and snake.check_danger(head_right, body_only)) or
                    (dir_down and snake.check_danger(head_left, body_only)) or
                    (dir_left and snake.check_danger(head_up, body_only)) or
                    (dir_right and snake.check_danger(head_down, body_only))
                )

        state = [
            # Current direction
            dir_left,
            dir_right,
            dir_up,
            dir_down,

            # Apple direction
            apple_pos[0] < snake.position[0],  # Apple left
            apple_pos[0] > snake.position[0],  # Apple right
            apple_pos[1] < snake.position[1],  # Apple up
            apple_pos[1] > snake.position[1]  # Apple down
        ]

        state.extend([snake.check_danger(square) for square in snake.near_space])

        return np.array(state, dtype=float)

    def remember(self, state, action: list, reward: int, new_state, game_over: bool):
        self.memory.append((state, action, reward, new_state, game_over))

    def train_long_memory(self):
        if len(self.memory) < BATCH_SIZE:
            return
        sample = random.sample(self.memory, BATCH_SIZE)
        states, actions, rewards, new_states, game_overs = zip(*sample)
        # self.trainer.train_step(*sample)
        self.trainer.train_step(states, actions, rewards, new_states, game_overs)

    def train_short_memory(self, state, action: list, reward: int, new_state, game_over: bool):
        self.trainer.train_step(state, action, reward, new_state, game_over)

    def get_action(self, state) -> list:
        action = [0, 0, 0]
        # Lower the randomness as games go up
        self.randomness = 200 - self.total_games if self.model_path is None else -1
        if random.randint(0, 200) < self.randomness:
            move = random.randint(0, 2)
            action[move] = 1
        else:
            state_tensor = torch.tensor(np.array(state), dtype=torch.float)
            prediction = self.model(state_tensor)
            move = torch.argmax(prediction).item()
            action[move] = 1

        return action


def train(model_path: str = None):
    total_score = 0
    best_score = 0
    plot_scores = []
    plot_mean_scores = []
    game = SnakeGame(ai=True)
    agent = Agent(game.snake.near_space_radius, model_path)
    update_every_x_games = 1
    while game.running:
        # Get old state
        old_state = agent.get_state(game)

        # Get next move
        next_move = agent.get_action(old_state)

        # Make move and retrieve results
        game_over, score, reward = game.tick(next_move)
        new_state = agent.get_state(game)

        # Train short memory
        agent.train_short_memory(old_state, next_move, reward, new_state, game_over)

        # Remember
        agent.remember(old_state, next_move, reward, new_state, game_over)

        if game_over:
            game.reset()
            agent.total_games += 1
            agent.train_long_memory()

            if score > best_score:
                best_score = score
                agent.model.save()

            total_score += score
            plot_scores.append(score)
            plot_mean_scores.append(total_score/agent.total_games)
            if agent.total_games % update_every_x_games == 0:
                helper.plot(plot_scores, plot_mean_scores)
    print(f"\n\nN° Games: {agent.total_games}\nBest: {best_score}\nAverage: {total_score / agent.total_games if agent.total_games > 0 else 0}")

def play(model_path: str):
    total_score = 0
    best_score = 0
    if not os.path.exists(model_path):
        print("Failed to find model at the given path")
        return
    game = SnakeGame(ai=True)
    agent = Agent(game.snake.near_space_radius, model_path)
    while game.running:
        # Get old state
        old_state = agent.get_state(game)

        # Get next move
        next_move = agent.get_action(old_state)

        # Make move and retrieve results
        game_over, score, reward = game.tick(next_move)

        if game_over:
            game.reset()
            agent.total_games += 1
            total_score += score

            if score > best_score:
                best_score = score
    print(f"\n\nN° Games: {agent.total_games}\nBest: {best_score}\nAverage: {total_score / agent.total_games if agent.total_games > 0 else 0}")



if __name__ == "__main__":
    # train()  # Create new model - Overwrite existing snake.pt
    train("models/current-GRID_25.pt")  # current (1100 + 120 + 140 + 1274)
    # play("models/snake 103 (GRID_25).pt")
