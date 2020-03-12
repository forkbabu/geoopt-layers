import torch_geometric.nn.conv
from .. import Distance2PoincareHyperplanes, WeightedPoincareCentroids
import torch
import collections
import inspect


class HyperbolicGraphConv(torch_geometric.nn.conv.MessagePassing):
    r"""The graph neural network operator from the `"Weisfeiler and Leman Go
    Neural: Higher-order Graph Neural Networks"
    <https://arxiv.org/abs/1810.02244>`_ paper

    .. math::
        \mathbf{x}^{\prime}_i = \mathbf{\Theta}_1 \mathbf{x}_i +
        \sum_{j \in \mathcal{N}(i)} \mathbf{\Theta}_2 \mathbf{x}_j.
    """

    def __init__(
        self,
        in_channels,
        out_channels,
        aggr="add",
        *,
        num_basis=None,
        ball,
        ball_out=None,
        nonlinearity=torch.nn.Identity(),
    ):
        if ball_out is None:
            ball_out = ball
        super(HyperbolicGraphConv, self).__init__(aggr=aggr)
        if num_basis is None:
            num_basis = out_channels
        self.num_basis = num_basis
        self.ball_in = ball
        self.ball_out = ball_out
        self.in_channels = in_channels
        self.out_channels = out_channels
        self.hyperplanes_loop = Distance2PoincareHyperplanes(
            in_channels, num_basis, ball=ball, scaled=True, squared=False
        )
        self.hyperplanes_neighbors = Distance2PoincareHyperplanes(
            in_channels, num_basis, ball=ball, scaled=True, squared=False
        )
        self.mixing = torch.nn.Linear(num_basis, num_basis)
        self.basis = WeightedPoincareCentroids(
            out_channels, num_basis, ball=ball_out, lincomb=True
        )
        self.nonlinearity = nonlinearity
        self.reset_parameters()

    @torch.no_grad()
    def reset_parameters(self):
        self.basis.reset_parameters_identity()
        self.mixing.weight.set_(
            torch.eye(
                self.num_basis,
                device=self.mixing.weight.device,
                dtype=self.mixing.weight.dtype,
            )
        )

    def forward(self, x, edge_index, edge_weight=None, size=None):
        """"""
        h = self.hyperplanes_neighbors(x)
        return self.propagate(
            edge_index, size=size, x=x, h=h, edge_weight=edge_weight
        )

    def message(self, h_j=None, edge_weight=None):
        return h_j if edge_weight is None else edge_weight.view(-1, 1) * h_j

    def update(self, aggr_out, x):
        y = self.hyperplanes_loop(x)
        aggr_out = aggr_out + y
        aggr_out = self.mixing(aggr_out)
        activations = self.nonlinearity(aggr_out)
        return self.basis(activations)

    def extra_repr(self) -> str:
        return "{} -> {}, local={local}, aggr={aggr}".format(
            self.in_channels, self.out_channels, **self.__dict__
        )

    def set_parameters_from_graph_conv(
        self, graph_conv: torch_geometric.nn.conv.GraphConv
    ):
        self.reset_parameters()
        self.hyperplanes_neighbors.set_parameters_from_linear_operator(
            graph_conv.weight.t()
        )
        self.hyperplanes_loop.set_parameters_from_linear_operator(
            graph_conv.lin.weight, graph_conv.lin.bias
        )

    @classmethod
    def from_graph_conv(
        cls,
        graph_conv: torch_geometric.nn.conv.GraphConv,
        nonlinearity=torch.nn.Identity(),
        *,
        ball,
        ball_out=None,
        num_basis=None,
    ):
        layer = cls(
            graph_conv.in_channels,
            graph_conv.out_channels,
            aggr=graph_conv.aggr,
            num_basis=num_basis,
            nonlinearity=nonlinearity,
            ball=ball,
            ball_out=ball_out,
        )
        layer.set_parameters_from_graph_conv(graph_conv)
        return layer
