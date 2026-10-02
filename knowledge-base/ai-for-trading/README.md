# AI for Trading — Study Notes

## Source & capture

- **Primary source:** QuantInsti, *AI for Trading: How It Works, Uses, Risks, and Skills Guide* —
  <https://www.quantinsti.com/articles/ai-for-trading/>
- **Captured:** 2026-10-02
- **How it was captured:** the page itself could not be downloaded from the environment these
  notes were written in. The notes are built from search-indexed excerpts of the article,
  plus closely related QuantInsti/Quantra pages (linked under *Further reading*).
  Passages marked **(article)** are close paraphrases of the article. Passages marked
  **(related)** come from the companion QuantInsti material. Read the original to fill gaps.

---

## 1. Core idea: hype vs. reality

- Headlines sell "self-learning algorithms that beat the market". The reality is more
  nuanced, and **in real markets the gap between AI hype and AI reality can be expensive.** (article)
- **AI in trading** = applying intelligent systems to tasks that used to need human
  thinking: analysing data, recognising patterns, making predictions, managing risk and
  executing trades. (article)
- Top quant firms (Renaissance Technologies, Two Sigma) put AI **on top of** solid quant
  foundations: statistical modelling, systematic strategy design and strict risk controls.
  AI is the top layer, not a replacement for those foundations. (article)
- **Bottom line:** *AI tools amplify skill; they do not replace it.* The edge is not the
  tool. It is the trader's ability to combine domain knowledge, statistical reasoning and
  disciplined experimentation with modern AI techniques. (article)

## 2. What machine learning actually does in markets

- ML learns patterns from **historical and alternative data** to estimate the
  **probability** of price direction, volatility or market regime. (article)
- It powers **trading signals, position sizing and risk models.** (article)
- Its predictions are **probabilistic, not guaranteed**. Models must be **validated
  out-of-sample** and paired with **risk controls**. (article)
- At the advanced end, **transformers, deep neural networks and reinforcement learning
  (RL)** analyse complex financial time series for tasks like dynamic portfolio
  allocation and execution optimisation. (article)

## 3. AI across the trading lifecycle (the 4 stages)

```
 Market data ──► Model prediction ──► Portfolio & risk ──► Order execution
 (features)      (signals / goals)    (allocation, RL)     (cost, impact, RL)
```

### Stage 1 — Market data processing
- ML models help extract useful **features**: momentum, volatility, regime indicators
  and sentiment signals.
- These features are the **inputs** to the prediction and optimisation models. (article)

### Stage 2 — Model prediction
- Some models predict **intermediate signals** (e.g. next-period direction). Others
  **optimise the end goal directly** (e.g. risk-adjusted return). (article)
- Work **step by step**, from basic ML up to deep learning, before using these models
  in live markets. (article)

### Stage 3 — Portfolio optimisation & risk management
- Classical methods are still relevant: **mean-variance optimisation** and
  **Black–Litterman**. (article)
- **Reinforcement learning** is increasingly used for **dynamic capital allocation**.
  RL agents learn policies that balance return and risk over time and adapt as market
  conditions change. (article)

### Stage 4 — Order execution
- AI execution models analyse **high-frequency data** to cut **transaction costs**,
  reduce **market impact** and adjust **order placement in real time**. (article)
- RL suits this stage especially well, because decisions must react instantly to
  changing liquidity. (article)

## 4. Families of AI used in trading (related)

| Family | What it is | Typical trading use |
|---|---|---|
| **Discriminative ML** (supervised) | Learns features → label, e.g. classification or regression | Direction/volatility prediction, signal generation |
| **Unsupervised ML** | Finds structure without labels, e.g. clustering | Regime detection, asset grouping |
| **Deep learning** | Neural networks, e.g. LSTMs, transformers | Complex time-series patterns |
| **Reinforcement learning** | An agent learns a policy from rewards | Dynamic allocation, execution |
| **Generative AI / LLMs** | Transformers with attention; finance-tuned models like **FinBERT** | News and sentiment analysis, earnings-call parsing, research summaries |
| **Agentic AI** | LLM agents that can use tools, reason and act toward a goal | Turning an idea into a backtest, research automation, multi-agent portfolio bots |

- **Discriminative vs. generative:** discriminative models predict. Generative models
  can simulate whole datasets. (related)
- **Agent roles in an agentic workflow** (related):
  - *Task agent:* repeatable actions such as data retrieval.
  - *Research agent:* gathers and summarises information such as indicator definitions.
  - *Code-generation agent:* turns a strategy idea into runnable backtest code.
  - *Evaluation agent:* reviews the outputs and suggests corrections.
- **Example multi-agent portfolio bot** (related): an Analyst agent (news + price) →
  a Portfolio agent (allocation) → an Execution agent (broker API, e.g. Alpaca) →
  a Notifier agent (reporting).
- **Why agents beat repeated prompting** (related): one LLM needs to be prompted over
  and over. An agentic system works as a coordinated team of specialists, with checks
  built in.

## 5. Risks & failure modes

- **Hype risk:** believing a model "beats the market" without evidence is expensive. (article)
- **Misapplication:** a model used wrongly, or without understanding real market
  dynamics, leads to costly mistakes. (article/related)
- **Overfitting:** the model learns noise in the historical data, so it looks great in
  the backtest and fails live. (related)
- **Look-ahead bias:** using information that was not available at decision time. (related)
- **Ignoring transaction costs:** slippage, fees and market impact wipe out paper edges. (related)
- **False certainty:** outputs are probabilities, so never size a position as if a
  prediction were a sure thing. (article)
- **Non-stationarity / regime change:** patterns decay as markets change, so models need
  ongoing re-validation. *(General quant principle that fits the article's stress on
  adaptation and out-of-sample validation.)*

**Mitigations:** out-of-sample and walk-forward testing, realistic cost modelling,
strict risk controls, a clear economic reason for every signal, and a step-by-step path
(ML → DL → RL) before going live.

## 6. Skills needed

Non-technical:
1. Clear **trading hypotheses** and **economic intuition** — why should this edge exist?
2. The ability to **critically evaluate model outputs**.
3. **Patience** to iterate, test and refine strategies.

Technical:
1. **Python + data analysis:** pandas, NumPy, Matplotlib.
2. **ML fundamentals:** supervised, unsupervised, RL; e.g. SVC, XGBoost, scikit-learn.
3. **Deep learning:** Keras / TensorFlow.
4. **Trading tooling:** TA-Lib for indicators; backtesting frameworks.
5. **NLP / LLMs:** CountVectorizer, Word2Vec, BERT/FinBERT; calling LLMs through APIs
   (nice to have, not required to start).
6. **Statistics & risk:** the base everything else sits on.

## 7. Suggested learning path (from QuantInsti's material)

1. Python + pandas/NumPy for market data.
2. Intro ML for trading: classification and regression signals, out-of-sample testing.
3. Feature engineering: momentum, volatility, regime and sentiment features.
4. Portfolio and risk: mean-variance, Black–Litterman, position sizing.
5. Deep learning for time series.
6. Reinforcement learning for allocation and execution.
7. LLMs/NLP for sentiment and research; then agentic workflows for idea → backtest.
8. Paper trade → small live → scale, with risk controls at every step.

## 8. Key takeaways (one-liners)

1. AI amplifies skill; it does not replace it.
2. Predictions are probabilities — validate out-of-sample and always use risk controls.
3. Think in the lifecycle: data → prediction → portfolio/risk → execution.
4. Classical methods (mean-variance, Black–Litterman) are still the baseline that AI must beat.
5. RL fits sequential decisions best: allocation and execution.
6. LLMs and agents speed up research; they do not prove an edge.
7. Every model needs an economic reason why the edge should exist.

## Self-check questions

1. What are the four stages of the AI trading lifecycle, and which AI technique fits each best?
2. Why must ML predictions be validated out-of-sample?
3. When would you use RL instead of a supervised classifier?
4. Name two classical portfolio methods that are still relevant alongside AI.
5. What do the four agent roles in an agentic research workflow do?
6. List three ways a backtest can lie (overfitting, look-ahead bias, ignored costs).
7. Why do firms like Renaissance and Two Sigma still lean on statistics and risk controls?

## Applying it to my journal

- For every trade or strategy, log the **hypothesis** (why the edge exists) and the
  **features** used: momentum, volatility, regime, sentiment.
- Log the **regime** at entry (trending/ranging, high/low volatility) so I can later
  test whether the edge depends on regime.
- Record **costs** (fees, slippage) on every trade — the main way paper edges die.
- If a model or AI tool produced the signal, record its **confidence/probability** and
  compare it with the real outcome over time to check calibration.
- Keep **in-sample vs. out-of-sample / live** results separate when reviewing a strategy.

## Further reading

- [AI for Trading: How It Works, Uses, Risks, and Skills Guide](https://www.quantinsti.com/articles/ai-for-trading/) (primary)
- [AI in Trading: Insights from Experts](https://www.quantinsti.com/articles/ai-in-trading-insights-from-experts/)
- [Agentic AI Portfolio Manager: Multi-Agent Trading Bot with Alpaca](https://www.quantinsti.com/articles/agentic-ai-portfolio-manager-alpaca-trading-bot/)
- [Build an MCP Server for Trading with Python and AI](https://www.quantinsti.com/articles/mcp-server-trading-python-ai/)
- [Trading Using LLM: Generative AI & Sentiment Analysis](https://blog.quantinsti.com/trading-using-llm/)
- [Hands-On AI Trading: Python, QuantConnect and AWS](https://blog.quantinsti.com/ai-quantitative-trading-python-quantconnect-aws/)
- [Quantra — Introduction to Machine Learning and AI for Trading](https://quantra.quantinsti.com/course/introduction-to-machine-learning-for-trading)
- [Quantra — Agentic AI for Trading](https://quantra.quantinsti.com/course/agentic-ai-trading)
- [Quantra — Artificial Intelligence in Trading Advanced (learning track)](https://quantra.quantinsti.com/learning-track/machine-learning-deep-learning-trading-2)
