#include <pybind11/pybind11.h>
#include <pybind11/numpy.h>

#include <cmath>
#include <stdexcept>
#include <vector>

namespace py = pybind11;

py::array_t<double> sample_covariance(
    py::array_t<double, py::array::c_style | py::array::forcecast> returns,
    double annualization_factor
) {
    auto r = returns.unchecked<2>();

    const py::ssize_t n_obs = r.shape(0);
    const py::ssize_t n_assets = r.shape(1);

    if (n_obs < 2) {
        throw std::runtime_error("sample_covariance requires at least 2 observations.");
    }

    std::vector<double> means(n_assets, 0.0);

    for (py::ssize_t i = 0; i < n_obs; ++i) {
        for (py::ssize_t j = 0; j < n_assets; ++j) {
            means[j] += r(i, j);
        }
    }

    for (py::ssize_t j = 0; j < n_assets; ++j) {
        means[j] /= static_cast<double>(n_obs);
    }

    py::array_t<double> result({n_assets, n_assets});
    auto cov = result.mutable_unchecked<2>();

    for (py::ssize_t a = 0; a < n_assets; ++a) {
        for (py::ssize_t b = a; b < n_assets; ++b) {
            double sum = 0.0;

            for (py::ssize_t i = 0; i < n_obs; ++i) {
                sum += (r(i, a) - means[a]) * (r(i, b) - means[b]);
            }

            const double value =
                (sum / static_cast<double>(n_obs - 1)) * annualization_factor;

            cov(a, b) = value;
            cov(b, a) = value;
        }
    }

    return result;
}

py::array_t<double> ewma_covariance(
    py::array_t<double, py::array::c_style | py::array::forcecast> returns,
    int min_history,
    double ewma_lambda,
    double annualization_factor
) {
    auto r = returns.unchecked<2>();

    const py::ssize_t n_obs = r.shape(0);
    const py::ssize_t n_assets = r.shape(1);

    if (ewma_lambda <= 0.0 || ewma_lambda >= 1.0) {
        throw std::runtime_error("ewma_lambda must be between 0 and 1 exclusive.");
    }

    if (min_history < 2) {
        throw std::runtime_error("min_history must be at least 2.");
    }

    if (n_obs < min_history) {
        throw std::runtime_error("Not enough observations for EWMA covariance.");
    }

    std::vector<double> means(n_assets, 0.0);

    for (int i = 0; i < min_history; ++i) {
        for (py::ssize_t j = 0; j < n_assets; ++j) {
            means[j] += r(i, j);
        }
    }

    for (py::ssize_t j = 0; j < n_assets; ++j) {
        means[j] /= static_cast<double>(min_history);
    }

    std::vector<double> cov(n_assets * n_assets, 0.0);

    for (py::ssize_t a = 0; a < n_assets; ++a) {
        for (py::ssize_t b = a; b < n_assets; ++b) {
            double sum = 0.0;

            for (int i = 0; i < min_history; ++i) {
                sum += (r(i, a) - means[a]) * (r(i, b) - means[b]);
            }

            const double value = sum / static_cast<double>(min_history - 1);

            cov[a * n_assets + b] = value;
            cov[b * n_assets + a] = value;
        }
    }

    for (py::ssize_t i = min_history; i < n_obs; ++i) {
        for (py::ssize_t a = 0; a < n_assets; ++a) {
            for (py::ssize_t b = a; b < n_assets; ++b) {
                const double outer = r(i, a) * r(i, b);

                const double updated =
                    ewma_lambda * cov[a * n_assets + b]
                    + (1.0 - ewma_lambda) * outer;

                cov[a * n_assets + b] = updated;
                cov[b * n_assets + a] = updated;
            }
        }
    }

    py::array_t<double> result({n_assets, n_assets});
    auto out = result.mutable_unchecked<2>();

    for (py::ssize_t a = 0; a < n_assets; ++a) {
        for (py::ssize_t b = 0; b < n_assets; ++b) {
            out(a, b) = cov[a * n_assets + b] * annualization_factor;
        }
    }

    return result;
}

PYBIND11_MODULE(fast_covariance_cpp, m) {
    m.doc() = "Fast covariance kernels for systematic backtesting";

    m.def(
        "sample_covariance",
        &sample_covariance,
        py::arg("returns"),
        py::arg("annualization_factor")
    );

    m.def(
        "ewma_covariance",
        &ewma_covariance,
        py::arg("returns"),
        py::arg("min_history"),
        py::arg("ewma_lambda"),
        py::arg("annualization_factor")
    );
}