# Optional learning experiments

Project ID: P11. Dependency: G3 plus accepted evaluator and sufficient reviewed corpus. Goal: measure whether learned proposals improve search efficiency. This project is optional and is not a prerequisite for the optimizer.

## P11-T01 Define the experiment before training

Choose the first experiment as a learned candidate ranker for selecting expensive evaluations. Its output is a proposal priority, not an authoritative performance score. Compare with the fixed non-learning P08 selection policy using the same candidate/evaluation budgets. Record data scope, split, feature schema, model choice, compute cost and pass criteria in an experiment manifest.

Default first model: a small gradient-boosted tree regressor over explicit numeric/categorical build features, with a pinned supported library selected and documented by the engineer. Use separate predictions for clear and boss scores; do not train a language model or add GPU infrastructure. A change to this experiment requires review of the concrete rationale.

Acceptance: reviewer approves the experiment design before training. Access/usage rights for training material are recorded. Training is skipped if validated labels or sufficiently separated build families are absent.

## P11-T02 Build a leakage resistant dataset

Generate examples from evaluated legal candidates and controlled mutations, including improvements and failures. Preserve provenance: simulator-derived labels remain simulator-derived; independently observed labels are distinct. Use classified legality/unsupported failures to train separate filtering if desired, not arbitrary negative DPS values.

Group by family/creator lineage/near-duplicate configuration and patch before splitting. Fit encoders/scalers on training only. Keep popularity, creator identity and source-provided DPS out of performance predictors. Record datasets and splits by content hash.

Acceptance: automated overlap checks find no duplicate or lineage leakage across splits. A current-patch model cannot silently include stale labels. Dataset documentation quantifies missing and biased coverage.

## P11-T03 Train and verify the ranker offline

Train reproducibly with a fixed seed and saved environment. Measure held-out ranking quality per family plus errors on unusual combinations. Compare against simple baseline selection before any integration. Measure training time and inference overhead.

Acceptance: artifact contains model, feature schema, catalog/evaluator compatibility, dataset hash and metrics. Unknown catalog features or incompatible patch/evaluator disable model use with a visible reason. Training success alone does not approve production integration.

## P11-T04 Compare complete searches

Integrate learned priorities only into the promising-candidate portion of P08. Preserve at least the existing 20% fresh proposal allocation and 16-of-64 detailed exploration slots. The model cannot reject legal candidates from all future exploration. Finalists always receive actual detailed evaluation and export checks.

Run at least five paired seeds per benchmark problem under equal detailed-evaluation and wall-clock budgets. Provisional adoption target: at least 20% fewer detailed evaluations to reach the non-learning baseline's target score, without lower final eligible score beyond run-to-run variation or reduced family coverage. Count training cost separately and estimate its amortization; do not hide it.

Acceptance: publish all paired results, successes and regressions. If the target is not demonstrated, leave the ranker disabled by default and retain the non-learning system. Reviewer may revise the target only prospectively with reasons.

## P11-T05 Document retraining and alternatives

Specify invalidation on patch, catalog, evaluator and feature changes. Retraining produces a new artifact and repeats held-out/search comparisons. Keep retrieval of source explanations independent of model weights so corrections do not require retraining.

If later proposing language-model fine-tuning or reinforcement learning for rotations, submit a separate experiment spec covering labels/reward, simulator exploitation, compute, evaluation and fallback. Do not treat guide imitation as evidence of superior builds.

Acceptance: disabling/removing the model leaves the core optimizer fully functional. Reports identify whether learned prioritization was used without upgrading confidence or optimality claims.
