# DecisionMirror

DecisionMirror is an interactive soccer analytics tool that explores how
the timing of substitutions can influence match outcomes.

The idea is simple. Substitutions are usually evaluated based on who was
brought on or taken off. But timing is just as important. What happens
if a substitution is made 10 minutes earlier? Or 8 minutes later? Would
the predicted win probability meaningfully change?

This project builds a mirror version of the match timeline and compares
the actual sequence of events to a counterfactual scenario where a
substitution occurs at a different minute.

------------------------------------------------------------------------

## Overview

DecisionMirror allows you to:

-   Load real World Cup 2022 matches
-   Detect key turning points in a match
-   Select a substitution event
-   Move that substitution within a bounded time window
-   Compare predicted win probability between actual and counterfactual
    timelines
-   Inspect model confidence and impact metrics

The goal is not to rewrite history, but to explore how sensitive match
outcomes are to tactical timing decisions.

------------------------------------------------------------------------

## How it works

The system is built around event-level data.

1.  Raw match events are loaded from StatsBomb data.
2.  Match states are constructed and stored in a processed dataset.
3.  Substitution events are extracted from the event stream.
4.  The simulation endpoint:
    -   Computes baseline outcome probabilities.
    -   Applies a minute shift to a selected substitution.
    -   Re-evaluates probabilities under the altered timeline.
5.  The frontend visualizes:
    -   Actual win probability
    -   Mirror win probability
    -   Final delta in win percentage
    -   Peak divergence
    -   Model confidence

When full probability curves are available, the system plots them across
the match timeline. If only final probabilities are available, it falls
back to a simplified comparison.

------------------------------------------------------------------------

## Technology Stack

Frontend: - Next.js with the App Router - TypeScript - Recharts for
visualization - Tailwind CSS

Backend: - FastAPI - Python - Parquet for processed state storage -
StatsBomb event data

------------------------------------------------------------------------

## Project Structure

backend/ app/ main.py statsbomb.py model_store.py data/ raw/statsbomb/
processed/states.parquet scripts/ fetch_wc2022_pack.py build_states.py

frontend/decisionmirror-ui/ app/page.tsx

------------------------------------------------------------------------

## Running Locally

### Backend

From the backend directory:

    python -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt

Fetch World Cup data and build processed states:

    python scripts/fetch_wc2022_pack.py
    python scripts/build_states.py

Start the API:

    uvicorn app.main:app --reload

The backend runs at:

    http://127.0.0.1:8000

Available endpoints:

    GET  /matches
    GET  /matches/{match_id}/subs
    GET  /matches/{match_id}/turning_points
    POST /simulate

------------------------------------------------------------------------

## Example Use Case

Load the 2022 World Cup Final and experiment with different substitution
timings. Move a late substitution earlier and observe how the predicted
win probability shifts. Examine the peak swing metric to see when the
divergence between timelines is largest.

This provides a structured way to think about tactical timing instead of
relying purely on intuition.

------------------------------------------------------------------------

## Interpretation Notes

-   Delta Win Percentage (end) shows the final predicted difference at
    full time.
-   Peak swing highlights the moment of greatest divergence between
    actual and mirror timelines.
-   Confidence reflects how stable or data-supported the prediction is.

This project is an exploratory analytics tool. It models probabilistic
scenarios rather than claiming causal certainty.

------------------------------------------------------------------------

## Future Directions

Potential extensions include:

Incorporating expected goals into the probability model
Modeling momentum using rolling possession value metrics
Classifying substitution types tactically
Building comparative decision profiles across managers
Extending to live match analysis

------------------------------------------------------------------------

## Author

DecisionMirror was built as an experimental sports analytics project
focused on counterfactual modeling and decision timing in football.
