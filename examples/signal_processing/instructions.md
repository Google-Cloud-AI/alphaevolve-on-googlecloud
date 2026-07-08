Evolve a signal processing algorithm that filters volatile, non-stationary
time series data using a sliding window approach.

## Problem

Filter noisy, non-stationary time series while:
- Minimizing spurious directional reversals (smoothness)
- Maintaining responsiveness with minimal lag
- Preserving genuine signal dynamics and trends
- Reducing phase delay

"Better" means a higher overall score combining composite J(theta),
smoothness, accuracy, noise reduction, and reliability.

## Function signature

```python
def process_signal(input_signal: np.ndarray, window_size: int) -> np.ndarray:
    """
    Args:
        input_signal: 1D numpy array of noisy signal samples.
        window_size: Number of samples in the processing window.

    Returns:
        Filtered signal as a 1D numpy array.
    """
```

Helper functions `adaptive_filter()` and
`enhanced_filter_with_trend_preservation()` may also be evolved.

## Constraints

- Must return a numpy array (not a list or scalar).
- Must not be empty.
- Each signal evaluation has a 10-second timeout.
- All values must be finite (no NaN or inf).

## Available libraries

- `numpy` (imported as `np`)
- `collections.deque`
- `scipy.signal` (imported as `signal`)

No other imports are allowed in the sandbox.

## Strategies to explore

- Adaptive filtering: Kalman filters, particle filters
- Multi-scale processing: wavelets, empirical mode decomposition (EMD)
- Predictive enhancement: polynomial fitting, local regression
- Trend detection: change-point detection, CUSUM
- Hybrid approaches: coarse-then-fine, ensemble of filters
- Exponentially weighted moving averages with adaptive decay

Known dead ends:
- Simple moving average alone has too much lag
- High-order polynomial fits overfit noise

## Multi-objective optimization function

```
J(theta) = alpha1 * S(theta) + alpha2 * L_recent(theta) + alpha3 * L_avg(theta) + alpha4 * R(theta)
```

- S(theta): Slope change penalty (directional reversals)
- L_recent(theta): Instantaneous lag error |y[n] - x[n]|
- L_avg(theta): Average tracking error (MAE over window)
- R(theta): False reversal penalty (mismatched trend changes)
- Weights: alpha1=0.3, alpha2=0.2, alpha3=0.2, alpha4=0.3

## Baselines

The seed program uses a weighted moving average with exponential weights
emphasizing recent samples. It achieves a moderate overall_score.
A good algorithm should exceed 0.5 overall_score.
