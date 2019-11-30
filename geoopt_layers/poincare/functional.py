import geoopt
import torch.nn.functional
import functools
from geoopt_layers.poincare import math


def mobius_adaptive_max_pool2d(input, output_size, return_indices=False):
    norms = input.norm(dim=1, keepdim=True, p=2)
    _, idx = torch.nn.functional.adaptive_max_pool2d(
        norms, output_size, return_indices=True
    )
    out = input.view(input.shape[0], input.shape[1], -1)
    out = out[
        torch.arange(input.shape[0], device=input.device).view((-1, 1, 1, 1)),
        torch.arange(input.shape[1], device=input.device).view((1, -1, 1, 1)),
        idx,
    ]
    if return_indices:
        return out, idx
    else:
        return out


def mobius_max_pool2d(
    input,
    kernel_size,
    stride=None,
    padding=0,
    dilation=1,
    ceil_mode=False,
    return_indices=False,
):
    norms = input.norm(dim=1, keepdim=True)
    _, idx = torch.nn.functional.max_pool2d(
        norms, kernel_size, stride, padding, dilation, ceil_mode, return_indices=True
    )
    out = input.view(input.shape[0], input.shape[1], -1)
    out = out[
        torch.arange(input.shape[0], device=input.device).view((-1, 1, 1, 1)),
        torch.arange(input.shape[1], device=input.device).view((1, -1, 1, 1)),
        idx,
    ]
    if return_indices:
        return out, idx
    else:
        return out


def mobius_avg_pool2d(
    input, kernel_size, stride=None, padding=0, ceil_mode=False, *, ball
):
    gamma = ball.lambda_x(input, dim=-3, keepdim=True)
    numerator = torch.nn.functional.avg_pool2d(
        input * gamma,
        kernel_size=kernel_size,
        stride=stride,
        padding=padding,
        ceil_mode=ceil_mode,
        count_include_pad=False,
    )
    denominator = torch.nn.functional.avg_pool2d(
        gamma - 1,
        kernel_size=kernel_size,
        stride=stride,
        padding=padding,
        ceil_mode=ceil_mode,
        count_include_pad=False,
    )
    output = numerator / denominator
    output = ball.mobius_scalar_mul(0.5, output, dim=-3)
    return output


def mobius_adaptive_avg_pool2d(input, output_size, *, ball):
    gamma = ball.lambda_x(input, dim=-3, keepdim=True)
    numerator = torch.nn.functional.adaptive_avg_pool2d(
        input * gamma, output_size=output_size
    )
    denominator = torch.nn.functional.adaptive_avg_pool2d(
        gamma - 1, output_size=output_size
    )
    output = numerator / denominator
    output = ball.mobius_scalar_mul(0.5, output, dim=-3)
    return output


def mobius_batch_norm_nd(
    input,
    running_midpoint,
    running_variance,
    beta1,
    beta2,
    alpha=None,
    bias=None,
    epsilon=1e-4,
    training=True,
    *,
    ball,
    n,
):
    dim = -n - 1
    if alpha is None:
        alpha = 1.0
    else:
        alpha = alpha.view(alpha.shape + (1,) * n)
    if training:
        reduce_dim = tuple(range(-n, 0)) + tuple(
            range(-input.dim(), -running_midpoint.dim() - n)
        )
        midpoint = math.poincare_mean(
            input, dim=dim, reducedim=reduce_dim, keepdim=True, ball=ball
        )
        variance = ball.dist2(midpoint, input, dim=dim, keepdim=True)
        variance = variance.mean(dim=reduce_dim, keepdim=True)
        input = ball.mobius_add(-midpoint, input, dim=dim)
        input = ball.mobius_scalar_mul(
            alpha / (variance + epsilon) ** 0.5, input, dim=dim
        )
        with torch.no_grad():
            running_variance.lerp_(variance.view_as(running_variance), beta1)
            running_midpoint.set_(
                ball.geodesic(
                    beta2, midpoint.view_as(running_midpoint), running_midpoint, dim=-1
                )
            )
    else:
        running_midpoint = running_midpoint.view(running_midpoint.shape + (1,) * n)
        running_variance = running_variance.view(running_variance.shape + (1,) * n)
        input = ball.mobius_add(-running_midpoint, input, dim=dim)
        input = ball.mobius_scalar_mul(
            alpha / (running_variance + epsilon) ** 0.5, input, dim=dim
        )
    if bias is not None:
        bias = bias.view(bias.shape + (1,) * n)
        input = ball.mobius_add(input, bias, dim=dim)
    return input


mobius_batch_norm = functools.partial(mobius_batch_norm_nd, n=0)
mobius_batch_norm1d = functools.partial(mobius_batch_norm_nd, n=1)
mobius_batch_norm2d = functools.partial(mobius_batch_norm_nd, n=2)


def mobius_linear(
    input,
    weight,
    bias=None,
    *,
    ball: geoopt.PoincareBall,
    ball_out: geoopt.PoincareBall,
    source_origin=None,
    target_origin=None,
):
    if source_origin is not None and target_origin is not None:
        # We need to take care of origins
        tangent = ball.logmap(source_origin, input)
        new_tangent = tangent @ weight
        if ball is ball_out:
            # In case same manifolds are used, we need to perform parallel transport
            new_tangent = ball.transp(source_origin, target_origin, new_tangent)
        output = ball_out.expmap(target_origin, new_tangent)
        if bias is not None:
            output = ball_out.mobius_add(output, bias)
    else:
        if ball is ball_out:
            output = ball.mobius_matvec(weight, input)
            if bias is not None:
                output = ball.mobius_add(output, bias)
        else:
            tangent = ball.logmap0(input)
            new_tangent = tangent @ weight
            output = ball_out.expmap0(new_tangent)
            if bias is not None:
                output = ball_out.mobius_add(output, bias)
    return output
