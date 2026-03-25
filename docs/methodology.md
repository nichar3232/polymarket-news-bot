# Mathematical Methodology

## 1. Bayesian Framework

### Why Likelihood Ratios?

A likelihood ratio (LR) answers: "How much more likely is this evidence under YES than under NO?"

- LR > 1: evidence favors YES
- LR = 1: evidence is neutral
- LR < 1: evidence favors NO

This is strictly correct Bayesian inference. Using a score (0.7 = "bullish") is not — it conflates the evidence with the conclusion.

### Signal Combination

```
log_posterior_odds = log_prior_odds + Σ(log(LR_i) × confidence_i × damping)

posterior_prob = sigmoid(log_posterior_odds)
```

Damping factor (0.85) accounts for inter-signal correlation. Without damping, correlated signals would produce overconfident posteriors.

## 2. VPIN Derivation

VPIN = Volume-synchronized Probability of Informed Trading (Easley, Lopez de Prado, O'Hara 2012)

**The core insight**: In markets with informed traders, order flow is systematically imbalanced. Uninformed traders are equally likely to buy or sell. Informed traders are not.

We detect this imbalance by partitioning trades into equal-volume buckets (not equal-time, which is more robust to varying activity).

```
VPIN = (1/n) × Σ |V_b^YES - V_b^NO| / V_bucket
```

Where:
- n = number of buckets (50 in our implementation)
- V_b^YES = YES-initiated volume in bucket b
- V_b^NO = NO-initiated volume in bucket b
- V_bucket = target bucket size

**LR mapping**:
```
vpin_strength = max(0, (VPIN - 0.3) / 0.7)      # normalize above threshold
lr = exp(2.0 × OFI × vpin_strength)
```

## 3. Cross-Market Signal Calibration

We treat alternative platforms as independent oracles.

Under the null hypothesis (markets are equally informed), Polymarket and Kalshi should agree.

A persistent disagreement suggests one market has seen information the other hasn't.

```
magnitude = |mean(kalshi_delta, metaculus_delta, manifold_delta)|
lr = exp(direction × magnitude × source_multiplier × 3.0)

source_multiplier:
  1 source:  0.7  (single source could be wrong)
  2 sources: 1.0  (consensus)
  3 sources: 1.3  (strong consensus)
```

**Why k=3.0?** Calibrated so that:
- 2 sources, 10% divergence → LR ≈ 1.35 (mild update)
- 2 sources, 20% divergence → LR ≈ 1.82 (moderate update)
- 3 sources, 15% divergence → LR ≈ 2.57 (strong update)

## 4. LLM Superforecaster Decomposition

### The Good Judgment Project Methodology

Philip Tetlock's research showed that elite forecasters ("superforecasters"):
1. Break questions into smaller, answerable pieces
2. Use outside view (base rates) as anchor
3. Update inside view based on specific evidence
4. Express calibrated uncertainty (not overconfident)

### Our Implementation

The LLM is prompted to output structured JSON with:
- `sub_claims`: list of independent conditions
- `joint_probability_inside_view`: combined estimate from sub-claims
- `outside_view_base_rate`: historical frequency of similar events
- `blended_probability`: 70% inside + 30% outside
- `confidence_interval`: 90% CI

### LR Conversion

```python
prior_odds = market_price / (1 - market_price)
llm_odds = blended_prob / (1 - blended_prob)
lr = llm_odds / prior_odds
```

This is correct: the LR represents how much the LLM's information shifts our belief relative to the crowd's starting point.

### Temperature = 0.1

We use very low temperature. Probability estimation is not a creative task. We want the LLM to produce its most considered, deterministic response given the facts.

## 5. Kelly Criterion

### Derivation

Kelly (1956) showed that the fraction f* = (b×p - q) / b maximizes expected log wealth.

This is equivalent to maximizing long-run geometric return (not arithmetic return).

### Why Fractional Kelly?

Full Kelly requires exact probability estimates. Our estimates have uncertainty.

If true probability = 0.60 but we estimate 0.65, full Kelly overbets.

Fractional Kelly (0.25×) is equivalent to assuming our estimates have ~4× more uncertainty than stated. This dramatically reduces variance while keeping most of the expected return.

### Simultaneous Bets

For n simultaneous bets, we apply an additional discount of 1/√n to account for portfolio correlation.

## 6. Wikipedia Edit Velocity

### Signal Theory

Breaking news appears on Wikipedia before most news outlets because:
1. Wikipedia editors monitor news feeds constantly
2. Anyone can edit immediately
3. Professional news sites have editorial cycles

Empirically, major events show 3-10× normal edit rates 5-15 minutes before mainstream coverage.

### Velocity Score

```python
baseline = edits_last_60min / 12    # average 5-min rate
velocity = edits_last_5min / baseline

is_spiking = velocity >= 3.0 AND edits_last_5min >= 3
```

The ≥3 edit floor prevents false positives from single vandal edits.

### Signal Direction

Wikipedia velocity alone doesn't tell us YES or NO. We use it as an amplifier:
- If other signals say YES + Wikipedia spikes → strengthen YES signal
- LR is capped at 1.5 (spike alone is uncertain)

## 7. GDELT Integration

GDELT processes 100+ global news sources every 15 minutes.

### GKG 2.0 Features Used

- **Themes**: CAMEO event code classification (e.g., ECON_INFLATION, PROTEST, ELECTION)
- **Tone**: Goldstein scale (-100 to +100)
- **Activity Reference Density**: prominence/salience of the story

### LR Mapping

```python
# Normalize tone to [-1, +1]
normalized_tone = max(-1, min(1, tone / 50))

# Apply with relevance weighting
lr = exp(normalized_tone × relevance × confidence × 2)
```

A Goldstein score of +30 (moderately positive) from a highly relevant, prominent story → LR ≈ 1.8.

## 8. Confidence Interval Computation

We compute 90% CI from signal disagreement:

```python
log_lrs = [log(eff_lr) for signal in signals]
std = std(log_lrs)  # measure of signal disagreement

# Convert log-odds std to probability std
prob_std = posterior × (1 - posterior) × std

half_width = 1.645 × prob_std  # 90% CI
```

Wide CI = signals disagree = be more cautious with position sizing.
