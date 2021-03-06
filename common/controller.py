import random
import numpy as np
from common.utils import extract_seeds


class DemoScheduler:
    """Demonstration Scheduler - used for predefined schedules for querying and learning"""

    def __init__(self, args, params, rollout, schedule='linear'):
        self.num_timesteps = args.num_timesteps
        self.num_demos = params.num_demo_queries
        self.demo_schedule = schedule
        self.demo_learn_ratio = params.demo_learn_ratio
        self.hot_start = params.hot_start
        self.rollout = rollout
        self.n_envs = params.n_envs
        self.n_steps = params.n_steps
        self.multi = params.demo_multi
        self.multi_seed_sampling = params.multi_seed_sampling
        self.seed_store = set()

        self.query_count = 0
        self.demo_learn_count = 0
        if self.hot_start:
            self.buffer_empty = False
        else:
            self.buffer_empty = True

    def query_demonstrator(self, curr_timestep):
        """Get a trajectory from the demonstrator"""
        if self.demo_schedule == 'linear':
            return self._linear_schedule(curr_timestep)
        else:
            raise NotImplementedError

    def learn_from_demos(self, curr_timestep, always_learn=False):
        """Learn from the replay buffer"""
        if always_learn:
            return True
        learn_every = (1 / self.demo_learn_ratio) * self.n_envs * self.n_steps
        if not self.multi and self.buffer_empty:
            return False
        else:
            if curr_timestep > ((self.demo_learn_count + 1) * learn_every):
                self.demo_learn_count += 1
                return True
            else:
                return False

    def store_seeds(self):
        info = self.rollout.info_batch[-1]
        seeds_list = extract_seeds(info)
        self.seed_store.update(seeds_list)

    def _linear_schedule(self, curr_timestep):
        """Linear Scheduler"""
        demo_every = self.num_timesteps // self.num_demos
        if curr_timestep > ((self.query_count + 1) * demo_every):
            self.buffer_empty = False
            self.query_count += 1
            return True
        else:
            return False

    def get_seeds(self, demos_per_step=2):
        if self.multi and self.multi_seed_sampling == 'latest':
            info = self.rollout.info_batch[-1]
            seeds = extract_seeds(info)
            return seeds
        elif self.multi and self.multi_seed_sampling == 'random':
            seeds = random.choices(tuple(self.seed_store), k=self.n_envs)
            return seeds
        elif not self.multi:
            envs = np.random.randint(0, self.n_envs, demos_per_step)
            seeds = []
            for env in envs:
                seed = self.rollout.info_batch[-1][env]['level_seed']
                seeds.append(seed)
            return seeds

    def get_stats(self):
        return self.query_count, self.demo_learn_count, 0.0


class GAEController:

    def __init__(self, args, params, rollout):
        self.rollout = rollout
        self.args = args
        self.n_envs = params.n_envs
        self.n_steps = params.n_steps
        self.adv_tracker = np.zeros(self.n_envs)
        self.count_tracker = np.zeros(self.n_envs)
        self.running_avg = 0.0
        self.weighting_coef = params.weighting_coef
        self.rho = params.rho
        self.t = 0
        self.demo_seeds = None

        self.demo_learn_ratio = params.demo_learn_ratio
        self.num_timesteps = args.num_timesteps
        self.num_demos = params.num_demo_queries
        self.hot_start = params.hot_start
        self.query_count = 0
        self.demo_learn_count = 0
        if self.hot_start:
            self.buffer_empty = False
        else:
            self.buffer_empty = True

    def _compute_avg_adv(self):
        adv_batch = self.rollout.adv_batch
        done_batch = self.rollout.done_batch
        info_batch = self.rollout.info_batch
        adv_list = []
        seed_list = []
        for i in range(self.n_envs):
            for j in range(self.n_steps):
                if not done_batch[j][i]:
                    self.count_tracker[i] += 1
                    self.adv_tracker[i] += (1 / self.count_tracker[i]) * (abs(adv_batch[j][i]) - self.adv_tracker[i])
                else:
                    seed = info_batch[j][i]['level_seed']
                    adv_list.append(self.adv_tracker[i])
                    seed_list.append(seed)
                    self.adv_tracker[i] = 0
                    self.count_tracker[i] = 0

        return adv_list, seed_list

    def _update_running_avg(self, adv_list):
        if adv_list:
            mean_adv_t = np.mean(adv_list)
            if self.t == 0:
                self.running_avg = mean_adv_t
                self.t += 1
            else:
                self.running_avg = self.weighting_coef * mean_adv_t + (1 - self.weighting_coef) * self.running_avg
                self.t += 1

    def _generate_demo_seeds(self):
        demo_seeds = []
        adv_list, seed_list = self._compute_avg_adv()
        self._update_running_avg(adv_list)
        for adv, seed in zip(adv_list, seed_list):
            if adv > self.rho * self.running_avg:
                demo_seeds.append(seed)

        self.demo_seeds = demo_seeds

    def query_demonstrator(self, curr_timestep):
        """Get a trajectory from the demonstrator"""
        self._generate_demo_seeds()
        if self.demo_seeds:
            self.query_count += len(self.demo_seeds)
            return True
        else:
            return False

    def learn_from_demos(self, curr_timestep, always_learn=False):
        """Learn from the replay buffer"""
        if always_learn:
            return True
        learn_every = (1 / self.demo_learn_ratio) * self.n_envs * self.n_steps
        if self.buffer_empty:
            return False
        else:
            if curr_timestep > ((self.demo_learn_count + 1) * learn_every):
                self.demo_learn_count += 1
                return True
            else:
                return False

    def get_seeds(self):
        return self.demo_seeds

    def get_stats(self):
        return self.query_count, self.demo_learn_count, self.running_avg


























