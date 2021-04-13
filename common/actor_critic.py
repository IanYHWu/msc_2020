import torch.nn as nn
import torch.nn.functional as F
from torch.distributions import Categorical
from common.utils import init


class CategoricalAC(nn.Module):
    def __init__(self, base, recurrent, num_actions):
        """
        embedder: (torch.Tensor) model to extract the embedding for observation - probably a ConvNet
        action_size: number of the categorical actions
        """
        super().__init__()
        self.base = base
        self.recurrent = recurrent
        self.dist = Categorical(self.base.output_size, num_actions)

    def is_recurrent(self):
        return self.recurrent

    def forward(self, x, hx, masks):
        value, actor_features, rnn_hxs = self.base(x, hx, masks)
        dist = self.dist(actor_features)
        value = value.reshape(-1)

        return dist, value, rnn_hxs


class FixedCategorical(Categorical):
    """
    Categorical distribution object
    """
    def sample(self):
        return super().sample().unsqueeze(-1)

    def log_probs(self, actions):
        return (
            super()
            .log_prob(actions.squeeze(-1))
            .view(actions.size(0), -1)
            .sum(-1)
            .unsqueeze(-1)
        )

    def mode(self):
        return self.probs.argmax(dim=-1, keepdim=True)


class Categorical(nn.Module):
    """
    Categorical distribution (NN module)
    """
    def __init__(self, num_inputs, num_outputs):
        super(Categorical, self).__init__()

        init_ = lambda m: init(
            m,
            nn.init.orthogonal_,
            lambda x: nn.init.constant_(x, 0),
            gain=0.01)

        self.linear = init_(nn.Linear(num_inputs, num_outputs))

    def forward(self, x):
        x = self.linear(x)
        return FixedCategorical(logits=x)
