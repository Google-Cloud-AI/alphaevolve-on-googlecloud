# Suitability and Architecture (Sections 1-2)

## 1. What AlphaEvolve Is

AlphaEvolve is an evolutionary coding agent that searches through spaces of possible programs to find solutions that optimize a user-defined objective. Unlike general coding agents that produce a single best-effort answer, AlphaEvolve runs an iterative evolutionary loop: it proposes code mutations via an LLM ensemble, evaluates them automatically, and uses the scores to guide future mutations over hundreds or thousands of generations.

The system was developed at Google DeepMind (Novikov et al., 2025) and has produced results including the first improvement to Strassen's matrix multiplication algorithm in 56 years (4x4 complex matrices in 48 scalar multiplications, down from 49), more efficient data center scheduling algorithms, and simplified TPU circuit designs.

AlphaEvolve is NOT a general-purpose code generator. It is a mathematical search and optimization tool. Candidate solutions are validated against numerical optimization targets, not against ground truth labels. The only critical inputs are the initial seed program and the evaluation function.

### 1.1 When AlphaEvolve Is the Right Tool

AlphaEvolve is well-suited when ALL of these conditions hold:

1. **The algorithm to optimize is representable as code under 4000 LOC.** AlphaEvolve's LLM ensemble needs to read and reason about the entire program. Larger codebases dilute the LLM's attention and produce lower-quality mutations.

2. **The evaluation function runs in O(10 minutes) or less.** Each candidate program must be evaluated to produce a score. If evaluation takes hours, the evolutionary loop is too slow to explore enough of the search space within a reasonable budget.

3. **The problem is non-convex and difficult to solve with existing methods.** If the search space is convex, a greedy method (gradient descent, linear programming) is guaranteed to converge and will outperform AlphaEvolve. AE is designed for problems where the landscape has multiple local optima, discontinuities, or combinatorial structure that defeats gradient-based approaches.

4. **The optimization objective can be expressed as a monotonic scoring function.** AlphaEvolve treats all problems as hill climbing. If you cannot define a numerical score that increases as solutions improve, AE cannot search effectively.

### 1.2 When AlphaEvolve Is NOT the Right Tool

Do not use AlphaEvolve for:

- **Convex optimization problems.** Standard solvers (scipy.optimize, CVXPY, Gurobi) will find the global optimum faster and with guarantees.
- **Needle-in-a-haystack problems.** If there is only one valid solution in the entire program space (e.g., prime factorization), evolutionary search is the wrong paradigm.
- **Over-constrained problems** where the space of valid solutions is extremely sparse. AE will spend most of its budget generating invalid programs.
- **Problems solvable by hyperparameter tuning.** If the search space is a small grid of parameters, use GridSearchCV or Optuna.
- **Code generation from scratch.** AE evolves existing code; it does not write programs from a blank slate.

### 1.3 AlphaEvolve vs. Other Approaches

| Approach | Best for | Limitation |
| --- | --- | --- |
| **AlphaEvolve** | Non-convex code optimization, algorithm discovery | Requires well-designed evaluator; 100-1000+ eval budget |
| **General coding agents** | One-shot code generation, debugging | No iterative optimization; single attempt |
| **Classical OR solvers** | Convex/LP/MIP with mathematical structure | Cannot handle arbitrary code as decision variables |
| **Bayesian optimization** | Hyperparameter tuning, continuous spaces | Fixed search space dimensionality |
| **Genetic programming** | Symbolic regression, small programs | Hand-designed mutation operators |

### 1.4 Search Space Topology Awareness

Before starting an experiment, reason about the structure of the solution space to avoid sending AlphaEvolve on unproductive searches:

| Topology | Description | AE Suitability |
| --- | --- | --- |
| **Single valid solution** | Only one correct answer exists (e.g., factorization) | Poor -- use exact methods |
| **Sparse/clustered** | Valid solutions are rare and isolated; problem is near a complexity phase transition | Marginal -- AE may struggle to find any valid solution |
| **Multiple local optima** | Many good solutions exist in different regions | Excellent -- this is AE's sweet spot |
| **Convex** | Any local optimum is the global optimum | Poor -- use gradient methods |
| **Large plateau** | Many solutions have similar scores | Needs better metric design to discriminate |

---

## 2. How AlphaEvolve Works

### 2.1 Architecture

AlphaEvolve has two sides:

**Server-side** (the AlphaEvolve Cloud API):
- Maintains the evolutionary population database
- Samples parent programs and constructs LLM prompts
- Calls the LLM ensemble to generate candidate mutations
- Applies mutations to produce new candidate programs
- Tracks scores and manages the evolutionary selection process

**Client-side** (your infrastructure):
- Acquires candidate programs from the API
- Runs them through your own evaluator (local, Cloud Run, GKE, etc.)
- Submits scores back via the SubmitEvaluations API endpoint

The controller orchestrates this loop: acquire a program, evaluate it on your infrastructure, submit the score back.

### 2.2 The Evolutionary Loop

Each generation cycle:

1. **Sample from database.** The system samples parent programs. One is the "root" (to be modified), others provide crossover context.

2. **Construct prompt.** The root program's code is included in full, with EVOLVE-BLOCK markers indicating mutable regions. Previous high-performing programs are shown for context. The prompt includes the problem description, user context, scores, and evaluation feedback from prior generations.

3. **Stochastic prompt diversification.** The prompt is automatically randomized to encourage exploration. The system varies task instructions, toggles chain-of-thought reasoning, and occasionally requests code simplification. This prevents the LLM from falling into repetitive mutation patterns.

4. **LLM generates mutations.** The ensemble selects a model (weighted random per-call) and produces code modifications targeting the mutable EVOLVE-BLOCK regions.

5. **Apply mutations.** Changes are applied to produce a new candidate program. Invalid or empty mutations are rejected.

6. **Evaluate.** The candidate is sent to the client for evaluation. The client runs the evaluator and submits scores and feedback back via the API.

7. **Register.** The scored program is added to the evolutionary database based on Pareto dominance and diversity criteria.

### 2.3 The Evolutionary Database

The database combines two algorithms to balance exploration and exploitation:

**MAP Elites** -- Keeps the single best program per metric. A new program replaces an existing one only if it is better on at least one metric and not worse on any. This maintains a diverse set of elite programs, each excelling on a different dimension.

**Islands** -- Maintains multiple independent subpopulations. Each island runs its own evolutionary process, preventing premature convergence. The system balances sampling between the global MAP Elites tracker and the island populations. Key mechanisms:

- Early generations sample more randomly (exploration); later generations focus on the best programs (exploitation).
- Under-explored regions of the search space get a sampling bonus.
- Periodic island resets re-seed all islands from the globally best individuals, preventing islands from getting stuck.

### 2.4 The LLM Ensemble

AlphaEvolve uses a weighted mixture of models. On each generation call, a model is selected probabilistically based on configured weights. This is per-call, not per-experiment -- every LLM invocation independently samples from the mixture.

### 2.5 Multi-File Program Support

Programs can span multiple files. EVOLVE-BLOCK markers determine which regions of which files the LLM can modify. Files without markers are preserved unchanged across generations.

The main program file must be named `initial_program.py`. The evaluator receives `--program-dir` pointing to a workspace containing all files and always exec's `initial_program.py`.
