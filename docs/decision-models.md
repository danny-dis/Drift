# Optional decision providers

Drift can ask a provider small, typed questions, such as how to classify a memory or which loop action to suggest. These answers are advice. They cannot grant tool access, spend past a call limit or approve their own work.

You do not need a decision provider to use Drift. The default configuration turns it off, and the local supervisor also disables it.

## What the code does

`DecisionService` in `drift/decisions.py` accepts boolean, choice and numeric-score questions. Each question needs a valid default. The service validates returned values and confidence, rejects non-finite numbers, and uses the defaults if a provider fails or returns an invalid answer.

A request contains at most 20 questions. State is limited to 6,000 characters and selected fields. Recognized credentials are filtered, but that does not make arbitrary private content safe to send remotely.

Remote providers need an explicit opt-in. Free-only mode blocks them. The optional Jev adapter is present; its presence does not prove that an account, endpoint or model is available. Remote calls still use Drift's call accounting.

## Settings

Keep these defaults unless you intend to configure and test a provider:

```yaml
decision_models_enabled: false
decision_remote_opt_in: false
jev_enabled: false
decisions_llm_fallback: false
```

`decision_local_only` can restrict an enabled provider to local use. `decision_max_state_chars` and `decision_allowed_state_fields` control the state sent to it. Raising a setting does not bypass the service's hard limits.

The dashboard's recorded decision data is available through `/api/ui/decisions`. It records observed results and fallback reasons; it does not turn keyword scores into probabilities or invent unmeasured accuracy. Evaluation code is in `drift/decision_eval.py`.

See [the loop](continuous-loop.md) and [safety settings](safety.md).
