from geoopt_layers.base import ManifoldModule
import geoopt
import torch


__all__ = [
    "Distance2PoincareHyperplanes",
    "Distance2PoincareHyperplanes1d",
    "Distance2PoincareHyperplanes2d",
    "Distance2PoincareHyperplanes3d",
]


class Distance2PoincareHyperplanes(ManifoldModule):
    n = 0

    def __init__(
        self,
        plane_shape: int,
        num_planes: int,
        signed=True,
        squared=False,
        *,
        ball,
        std=1.0,
        zero=False
    ):
        super().__init__()
        self.signed = signed
        self.squared = squared
        self.ball = ball
        self.plane_shape = geoopt.utils.size2shape(plane_shape)
        self.num_planes = num_planes
        self.points = geoopt.ManifoldParameter(
            torch.empty(num_planes - zero, plane_shape), manifold=self.ball
        )
        self.zero = zero
        tangent = torch.empty_like(self.points)
        self.sphere = sphere = geoopt.manifolds.Sphere()
        self.tangents = geoopt.ManifoldParameter(tangent, manifold=sphere)
        self.std = std
        self.reset_parameters()

    def forward(self, input):
        input_p = input.unsqueeze(-self.n - 1)
        point = self.points.permute(1, 0)
        point = point.view(point.shape + (1,) * self.n)
        tangent = self.tangents.permute(1, 0)
        tangent = tangent.view(tangent.shape + (1,) * self.n)

        distance = self.ball.dist2plane(
            x=input_p, p=point, a=tangent, signed=self.signed, dim=-self.n - 2
        )
        if self.squared and self.signed:
            sign = distance.sign()
            distance = distance ** 2 * sign
        elif self.squared:
            distance = distance ** 2
        if self.zero:
            distance_zero = self.ball.dist0(input, dim=-self.n - 1, keepdim=True)
            if self.squared:
                distance_zero = distance_zero ** 2
            distance = torch.cat([distance_zero, distance], dim=-self.n - 1)
        return distance

    def extra_repr(self):
        return (
            "plane_shape={plane_shape}, "
            "num_planes={num_planes}, "
            "zero={zero}, ".format(**self.__dict__)
        )

    @torch.no_grad()
    def reset_parameters(self):
        direction = torch.randn_like(self.points)
        direction /= direction.norm(dim=-1, keepdim=True)
        distance = torch.empty_like(self.points[..., 0]).normal_(
            std=self.std / (2 / 3.14) ** 0.5
        )
        self.points.set_(self.ball.expmap0(direction * distance.unsqueeze(-1)))
        if self.tangents is not None:
            # this is a good initialization
            # without it you usually get stuck in strange optimum
            self.tangents.copy_(self.points).proj_()


class Distance2PoincareHyperplanes1d(Distance2PoincareHyperplanes):
    n = 1


class Distance2PoincareHyperplanes2d(Distance2PoincareHyperplanes):
    n = 2


class Distance2PoincareHyperplanes3d(Distance2PoincareHyperplanes):
    n = 3
