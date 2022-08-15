import numpy as np
import matplotlib.pyplot as plt
from loco_hd import LoCoHD


def main():

    param_sets = [
        ("hyper_exp", [1., 1.]),
        ("hyper_exp", [1., 1/5]),
        ("hyper_exp", [1., 2., 1/7, 1/12]),
        ("dagum", [2., 1., 0.5]),
        ("dagum", [13.4, 6.4, 16.2]),
        ("uniform", [0., 5.]),
        ("uniform", [3., 7.]),
        ("kumaraswamy", [0., 5., 2., 5.]),
        ("kumaraswamy", [3., 7., 2., 2.]),
    ]

    x_delta = 0.01
    x_values = np.arange(0., 12., x_delta)

    for param_set in param_sets:

        fig, ax = plt.subplots()
        lchd = LoCoHD([], param_set)

        y_values = np.array(lchd.test_integrator(x_values))
        y_prime_values = (y_values[1:] - y_values[:-1]) / x_delta

        ax.plot(x_values, y_values)
        ax.plot(x_values[1:], y_prime_values)

        test_name = f"{param_set[0]}_p{'p'.join(map(str, param_set[1]))}.png"

        fig.savefig(f"./workdir/integrator_tests/{test_name}", dpi=300)


if __name__ == "__main__":
    main()
