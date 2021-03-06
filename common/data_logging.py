import numpy as np
import pandas as pd
from collections import deque
from common.arguments import parser
import time
import os
import torch
import json
import yaml
import wandb


class Logger:

    def __init__(self, args, params, log_wandb=False):
        self.start_time = time.time()
        self.params = params
        self.args = args
        self.root = self.args.log_dir
        self.name = self.args.name
        self.root_path = None
        self.checkpoint_path = None
        self.log_path = None
        self.demo_log_path = None
        self.n_envs = params.n_envs
        self.log_wandb = log_wandb

        self.episode_rewards = []
        for _ in range(params.n_envs):
            self.episode_rewards.append([])
        self.episode_len_buffer = deque(maxlen=40)
        self.episode_reward_buffer = deque(maxlen=40)

        self.eval_rewards = []
        self.eval_lens = []

        self.curr_timestep = 0
        self.num_episodes = 0

        self._make_dirs()

        if self.log_wandb:
            self._initialise_wandb()

    def _eval_reset(self):
        self.eval_rewards = []
        self.eval_lens = []

    def _make_dirs(self):
        root_path = self.root + '/' + self.name
        if not os.path.isdir(root_path):
            os.makedirs(root_path)
        checkpoint_path = root_path + '/checkpoint'
        if not os.path.isdir(checkpoint_path):
            os.makedirs(checkpoint_path)
        self.root_path = root_path
        self.checkpoint_path = checkpoint_path + '/checkpoint'
        self.log_path = self.root_path + '/' + self.name + '.csv'
        self.demo_log_path = self.root_path + '/' + self.name + '_demos.csv'

    def save_checkpoint(self, model, curr_timestep):
        torch.save({
            'model_state_dict': model.state_dict(),
            'curr_timestep': curr_timestep,
            'len_buffer': self.episode_len_buffer,
            'rew_buffer': self.episode_reward_buffer,
            'num_episodes': self.num_episodes
        }, self.checkpoint_path)

    def save_args(self):
        with open(self.root_path + '/input_args.txt', 'w') as f:
            json.dump(self.args.__dict__, f, indent=2)

    def load_checkpoint(self, model):
        checkpoint = torch.load(self.checkpoint_path)
        model.load_state_dict(checkpoint['model_state_dict'])
        curr_timestep = checkpoint['curr_timestep']
        len_buffer = checkpoint['len_buffer']
        rew_buffer = checkpoint['rew_buffer']
        num_episodes = checkpoint['num_episodes']

        self.episode_len_buffer = len_buffer
        self.episode_reward_buffer = rew_buffer
        self.num_episodes = num_episodes
        self.curr_timestep = curr_timestep

        return model, curr_timestep

    def feed(self, rew_batch, done_batch, eval_reward=None, eval_len=None):
        steps = rew_batch.shape[0]
        rew_batch = rew_batch.T
        done_batch = done_batch.T

        for i in range(self.n_envs):
            for j in range(steps):
                self.episode_rewards[i].append(rew_batch[i][j])
                if done_batch[i][j]:
                    self.episode_len_buffer.append(len(self.episode_rewards[i]))
                    self.episode_reward_buffer.append(np.sum(self.episode_rewards[i]))
                    self.episode_rewards[i] = []
                    self.num_episodes += 1
        self.eval_rewards.append(eval_reward)
        self.eval_lens.append(eval_len)
        self.curr_timestep += (self.n_envs * steps)

    def _check_log_exists(self):
        if os.path.isfile(self.log_path):
            return True
        else:
            return False

    def _check_demo_log_exists(self):
        if os.path.isfile(self.demo_log_path):
            return True
        else:
            return False

    def log_results(self):
        wall_time = time.time() - self.start_time
        if self.num_episodes > 0:
            episode_statistics = self._get_episode_statistics()
            episode_statistics_list = list(episode_statistics.values())
        else:
            if self.args.evaluate:
                episode_statistics_list = [None] * 8
            else:
                episode_statistics_list = [None] * 6

        results = [self.curr_timestep] + [wall_time] + [self.num_episodes] + episode_statistics_list
        if self._check_log_exists():
            df = pd.read_csv(self.log_path, index_col=0)
            df = df[df.timesteps != self.curr_timestep]
            df.loc[len(df)] = np.array(results)
            df.to_csv(self.log_path)
        else:
            if self.args.evaluate:
                df = pd.DataFrame(np.array([results]),
                                  columns=['timesteps', 'wall_time', 'num_train_episodes',
                                           'train_max_episode_rewards', 'train_mean_episode_rewards',
                                           'train_min_episode_rewards', 'train_max_episode_len',
                                           'train_mean_episode_len', 'train_min_episode_len',
                                           'test_mean_episode_rewards', 'test_mean_episode_len'])
            else:
                df = pd.DataFrame(np.array([results]),
                                  columns=['timesteps', 'wall_time', 'num_train_episodes',
                                           'train_max_episode_rewards', 'train_mean_episode_rewards',
                                           'train_min_episode_rewards',
                                           'train_max_episode_len', 'train_mean_episode_len', 'train_min_episode_len'])
            df.to_csv(self.log_path)

        if self.log_wandb:
            if self.args.evaluate:
                wandb.log({'timesteps': self.curr_timestep,
                           'train_mean_episode_rewards': episode_statistics_list[1],
                           'train_mean_episode_len': episode_statistics_list[4],
                           'test_mean_episode_rewards': episode_statistics_list[6],
                           'test_mean_episode_len': episode_statistics_list[7]})
            else:
                wandb.log({'timesteps': self.curr_timestep,
                           'train_mean_episode_rewards': episode_statistics_list[1],
                           'train_mean_episode_len': episode_statistics_list[4]})

        self._eval_reset()

    def _get_episode_statistics(self):
        if self.args.evaluate:
            episode_statistics = {'Train Rewards/max_episodes': np.max(self.episode_reward_buffer),
                                  'Train Rewards/mean_episodes': np.mean(self.episode_reward_buffer),
                                  'Train Rewards/min_episodes': np.min(self.episode_reward_buffer),
                                  'Train Len/max_episodes': np.max(self.episode_len_buffer),
                                  'Train Len/mean_episodes': np.mean(self.episode_len_buffer),
                                  'Train Len/min_episodes': np.min(self.episode_len_buffer),
                                  'Test Rewards/mean_episodes': np.mean(self.eval_rewards),
                                  'Test Len/mean_episodes': np.mean(self.eval_lens)}
        else:
            episode_statistics = {'Train Rewards/max_episodes': np.max(self.episode_reward_buffer),
                                  'Train Rewards/mean_episodes': np.mean(self.episode_reward_buffer),
                                  'Train Rewards/min_episodes': np.min(self.episode_reward_buffer),
                                  'Train Len/max_episodes': np.max(self.episode_len_buffer),
                                  'Train Len/mean_episodes': np.mean(self.episode_len_buffer),
                                  'Train Len/min_episodes': np.min(self.episode_len_buffer)}

        return episode_statistics

    def log_demo_stats(self, num_queries, num_learn, score):
        results = [self.curr_timestep] + [num_queries] + [num_learn] + [score]
        if self._check_demo_log_exists():
            df = pd.read_csv(self.demo_log_path, index_col=0)
            df = df[df.timesteps != self.curr_timestep]
            df.loc[len(df)] = np.array(results)
            df.to_csv(self.demo_log_path)
        else:
            df = pd.DataFrame(np.array([results]),
                              columns=['timesteps', 'num_queries', 'num_learn', 'score'])
            df.to_csv(self.demo_log_path)

        if self.log_wandb:
            wandb.log({'timesteps': self.curr_timestep,
                       'num_queries': num_queries,
                       'num_learn': num_learn,
                       'score': score})

    def _initialise_wandb(self):
        if self.args.load_checkpoint:
            wandb_id = self.params.wandb_id
            wandb.init(project=self.args.wandb_project_name, name=self.args.wandb_name, resume="must", id=wandb_id)
        else:
            wandb.init(project=self.args.wandb_project_name, name=self.args.wandb_name,
                       settings=wandb.Settings(start_method='fork'))
            wandb_id = wandb.util.generate_id()
            self.params.wandb_id = wandb_id
        wandb.config.update(self.params)
        wandb.config.update(self.args)


def load_args(root_path):
    args = parser.parse_args()
    print(args)
    with open(root_path + '/input_args.txt', 'r') as f:
        args.__dict__ = json.load(f)

    return args

