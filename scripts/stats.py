from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import pingouin as pg
from scipy.stats import chi2, norm, pearsonr
from sklearn.metrics import cohen_kappa_score
from statsmodels.formula.api import mixedlm
from statsmodels.stats.multitest import multipletests


QUALITY_FIELDS = [
    "clarity",
    "completeness",
    "actionability",
    "testability",
    "faithfulness",
]

BACKEND_ORDER = [
    "anthropic",
    "openai",
    "google",
]

BACKEND_LABELS = {
    "anthropic": "Claude",
    "openai": "GPT",
    "google": "Gemini",
}


def load_evaluator(path: Path, evaluator: str) -> pd.DataFrame:
    df = pd.read_csv(path)

    required = {"artifact_id", *QUALITY_FIELDS}
    missing = required - set(df.columns)

    if missing:
        raise ValueError(
            f"{path} is missing columns: {sorted(missing)}"
        )

    if df["artifact_id"].duplicated().any():
        raise ValueError(
            f"Duplicate artifact IDs found in {path}."
        )

    for field in QUALITY_FIELDS:
        df[field] = pd.to_numeric(
            df[field],
            errors="raise",
        )

        if not df[field].between(1, 5).all():
            raise ValueError(
                f"{field} contains values outside 1--5 in {path}."
            )

    df = df[
        ["artifact_id", *QUALITY_FIELDS]
    ].copy()

    df = df.rename(
        columns={
            field: f"{field}_{evaluator}"
            for field in QUALITY_FIELDS
        }
    )

    return df


def load_master(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)

    required = {
        "artifact_id",
        "requirement_id",
        "backend",
        "model",
        "repetition",
    }

    missing = required - set(df.columns)

    if missing:
        raise ValueError(
            f"{path} is missing columns: {sorted(missing)}"
        )

    if df["artifact_id"].duplicated().any():
        raise ValueError(
            "Duplicate artifact IDs found in master dataset."
        )

    return df


def merge_data(
    master: pd.DataFrame,
    eval1: pd.DataFrame,
    eval2: pd.DataFrame,
) -> pd.DataFrame:
    ids_master = set(master["artifact_id"])
    ids_eval1 = set(eval1["artifact_id"])
    ids_eval2 = set(eval2["artifact_id"])

    if ids_master != ids_eval1:
        raise ValueError(
            "Evaluator 1 artifact IDs do not match the master dataset."
        )

    if ids_master != ids_eval2:
        raise ValueError(
            "Evaluator 2 artifact IDs do not match the master dataset."
        )

    df = master.merge(
        eval1,
        on="artifact_id",
        validate="one_to_one",
    )

    df = df.merge(
        eval2,
        on="artifact_id",
        validate="one_to_one",
    )

    for field in QUALITY_FIELDS:
        df[field] = (
            df[f"{field}_e1"]
            + df[f"{field}_e2"]
        ) / 2

    df["overall"] = df[
        QUALITY_FIELDS
    ].mean(axis=1)

    df["overall_e1"] = df[
        [f"{field}_e1" for field in QUALITY_FIELDS]
    ].mean(axis=1)

    df["overall_e2"] = df[
        [f"{field}_e2" for field in QUALITY_FIELDS]
    ].mean(axis=1)

    df["backend"] = pd.Categorical(
        df["backend"],
        categories=BACKEND_ORDER,
        ordered=True,
    )

    return df


def descriptive_statistics(
    df: pd.DataFrame,
) -> pd.DataFrame:
    rows = []

    for backend in BACKEND_ORDER:
        subset = df[
            df["backend"] == backend
        ]

        row = {
            "backend": backend,
            "n": len(subset),
        }

        for field in [
            *QUALITY_FIELDS,
            "overall",
        ]:
            row[f"{field}_mean"] = subset[field].mean()
            row[f"{field}_sd"] = subset[field].std(ddof=1)

        rows.append(row)

    return pd.DataFrame(rows)


def evaluator_specific_means(
    df: pd.DataFrame,
) -> pd.DataFrame:
    rows = []

    for backend in BACKEND_ORDER:
        subset = df[
            df["backend"] == backend
        ]

        rows.append({
            "backend": backend,
            "evaluator_1": subset["overall_e1"].mean(),
            "evaluator_2": subset["overall_e2"].mean(),
        })

    return pd.DataFrame(rows)


def fit_mixed_model(
    df: pd.DataFrame,
    outcome: str,
):
    formula = (
        f'{outcome} ~ '
        'C(backend, Treatment(reference="anthropic"))'
    )

    model = mixedlm(
        formula,
        data=df,
        groups=df["requirement_id"],
    )

    last_error = None

    for method in [
        "lbfgs",
        "powell",
        "cg",
    ]:
        try:
            result = model.fit(
                reml=False,
                method=method,
                maxiter=2000,
                disp=False,
            )

            if result.converged:
                return result

        except Exception as exc:
            last_error = exc

    if last_error is not None:
        raise last_error

    raise RuntimeError(
        f"Mixed model did not converge for {outcome}."
    )


def global_backend_test(
    df: pd.DataFrame,
    outcome: str,
    full_result,
) -> tuple[float, float]:
    null_model = mixedlm(
        f"{outcome} ~ 1",
        data=df,
        groups=df["requirement_id"],
    )

    null_result = null_model.fit(
        reml=False,
        method="lbfgs",
        maxiter=2000,
        disp=False,
    )

    lr = 2 * (
        full_result.llf
        - null_result.llf
    )

    p = chi2.sf(
        lr,
        df=2,
    )

    return lr, p


def backend_design_vector(
    backend: str,
    parameter_names: list[str],
) -> np.ndarray:
    vector = np.zeros(
        len(parameter_names)
    )

    intercept_index = parameter_names.index(
        "Intercept"
    )

    vector[intercept_index] = 1

    if backend != "anthropic":
        marker = f"[T.{backend}]"

        parameter = next(
            name
            for name in parameter_names
            if marker in name
        )

        vector[
            parameter_names.index(parameter)
        ] = 1

    return vector


def pairwise_backend_comparisons(
    result,
) -> pd.DataFrame:
    parameter_names = list(
        result.fe_params.index
    )

    beta = result.fe_params.loc[
        parameter_names
    ].to_numpy()

    covariance = result.cov_params().loc[
        parameter_names,
        parameter_names,
    ].to_numpy()

    pairs = [
        ("anthropic", "openai"),
        ("anthropic", "google"),
        ("openai", "google"),
    ]

    rows = []

    for first, second in pairs:
        first_vector = backend_design_vector(
            first,
            parameter_names,
        )

        second_vector = backend_design_vector(
            second,
            parameter_names,
        )

        contrast = (
            first_vector
            - second_vector
        )

        estimate = float(
            contrast @ beta
        )

        variance = float(
            contrast
            @ covariance
            @ contrast
        )

        se = np.sqrt(variance)
        z = estimate / se

        p = 2 * norm.sf(
            abs(z)
        )

        ci_low = estimate - 1.96 * se
        ci_high = estimate + 1.96 * se

        rows.append({
            "comparison": (
                f"{BACKEND_LABELS[first]} - "
                f"{BACKEND_LABELS[second]}"
            ),
            "difference": estimate,
            "se": se,
            "ci_low": ci_low,
            "ci_high": ci_high,
            "z": z,
            "p": p,
        })

    table = pd.DataFrame(rows)

    table["p_holm"] = multipletests(
        table["p"],
        method="holm",
    )[1]

    return table


def weighted_kappa(
    eval1: pd.DataFrame,
    eval2: pd.DataFrame,
) -> pd.DataFrame:
    merged = eval1.merge(
        eval2,
        on="artifact_id",
        validate="one_to_one",
    )

    rows = []

    for field in QUALITY_FIELDS:
        kappa = cohen_kappa_score(
            merged[f"{field}_e1"],
            merged[f"{field}_e2"],
            weights="linear",
        )

        rows.append({
            "dimension": field,
            "weighted_kappa": kappa,
        })

    return pd.DataFrame(rows)


def icc_table(
    df: pd.DataFrame,
) -> pd.DataFrame:
    rows = []

    outcomes = [
        *QUALITY_FIELDS,
        "overall",
    ]

    for field in outcomes:
        if field == "overall":
            scores_e1 = df["overall_e1"]
            scores_e2 = df["overall_e2"]
        else:
            scores_e1 = df[f"{field}_e1"]
            scores_e2 = df[f"{field}_e2"]

        long_df = pd.DataFrame({
            "artifact_id": list(df["artifact_id"]) * 2,
            "evaluator": (
                ["E1"] * len(df)
                + ["E2"] * len(df)
            ),
            "score": pd.concat(
                [
                    scores_e1,
                    scores_e2,
                ],
                ignore_index=True,
            ),
        })

        icc = pg.intraclass_corr(
            data=long_df,
            targets="artifact_id",
            raters="evaluator",
            ratings="score",
        )

        icc_absolute = icc[
            icc["Type"] == "ICC(A,1)"
        ].iloc[0]

        rows.append({
            "dimension": field,
            "icc_2_1": icc_absolute["ICC"],
            "ci95": str(icc_absolute["CI95"]),
            "p": icc_absolute["pval"],
        })

    return pd.DataFrame(rows)


def ceiling_statistics(
    eval1: pd.DataFrame,
    eval2: pd.DataFrame,
) -> pd.DataFrame:
    merged = eval1.merge(
        eval2,
        on="artifact_id",
        validate="one_to_one",
    )

    rows = []

    for field in QUALITY_FIELDS:
        ratings = pd.concat(
            [
                merged[f"{field}_e1"],
                merged[f"{field}_e2"],
            ],
            ignore_index=True,
        )

        rows.append({
            "dimension": field,
            "ratings_4_or_5": (
                ratings >= 4
            ).mean(),
            "ratings_5": (
                ratings == 5
            ).mean(),
        })

    return pd.DataFrame(rows)


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--eval1",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--eval2",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--master",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("results/backend_analysis"),
    )

    args = parser.parse_args()

    eval1 = load_evaluator(
        args.eval1,
        "e1",
    )

    eval2 = load_evaluator(
        args.eval2,
        "e2",
    )

    master = load_master(
        args.master,
    )

    df = merge_data(
        master,
        eval1,
        eval2,
    )

    args.output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    print("=" * 70)
    print("ARTIFACT-LEVEL DESCRIPTIVE STATISTICS")
    print("=" * 70)

    descriptive = descriptive_statistics(
        df
    )

    pd.set_option(
        "display.max_columns",
        None,
    )

    print(
        descriptive.round(3).to_string(
            index=False
        )
    )

    descriptive.to_csv(
        args.output_dir
        / "backend_descriptive_statistics.csv",
        index=False,
    )

    print()
    print("=" * 70)
    print("EVALUATOR-SPECIFIC OVERALL MEANS")
    print("=" * 70)

    evaluator_means = evaluator_specific_means(
        df
    )

    print(
        evaluator_means.round(3).to_string(
            index=False
        )
    )

    evaluator_means.to_csv(
        args.output_dir
        / "evaluator_specific_means.csv",
        index=False,
    )

    print()
    print("=" * 70)
    print("MIXED-EFFECTS MODEL: OVERALL QUALITY")
    print("=" * 70)

    overall_model = fit_mixed_model(
        df,
        "overall",
    )

    print(
        overall_model.summary()
    )

    lr, global_p = global_backend_test(
        df,
        "overall",
        overall_model,
    )

    print()
    print(
        f"Global likelihood-ratio test: "
        f"chi2(2) = {lr:.3f}, "
        f"p = {global_p:.6f}"
    )

    pairwise = pairwise_backend_comparisons(
        overall_model
    )

    print()
    print(
        pairwise.round(4).to_string(
            index=False
        )
    )

    pairwise.to_csv(
        args.output_dir
        / "overall_pairwise_comparisons.csv",
        index=False,
    )

    print()
    print("=" * 70)
    print("DIMENSION-SPECIFIC MIXED MODELS")
    print("=" * 70)

    dimension_rows = []

    for field in QUALITY_FIELDS:
        result = fit_mixed_model(
            df,
            field,
        )

        lr, p = global_backend_test(
            df,
            field,
            result,
        )

        dimension_rows.append({
            "dimension": field,
            "lr_chi2": lr,
            "df": 2,
            "p": p,
        })

    dimension_tests = pd.DataFrame(
        dimension_rows
    )

    print(
        dimension_tests.round(4).to_string(
            index=False
        )
    )

    dimension_tests.to_csv(
        args.output_dir
        / "dimension_global_tests.csv",
        index=False,
    )

    print()
    print("=" * 70)
    print("LINEARLY WEIGHTED COHEN'S KAPPA")
    print("=" * 70)

    kappas = weighted_kappa(
        eval1,
        eval2,
    )

    print(
        kappas.round(3).to_string(
            index=False
        )
    )

    kappas.to_csv(
        args.output_dir
        / "weighted_kappa.csv",
        index=False,
    )

    print()
    print("=" * 70)
    print("ICC(2,1)")
    print("=" * 70)

    icc = icc_table(
        df
    )

    print(
        icc.round(3).to_string(
            index=False
        )
    )

    icc.to_csv(
        args.output_dir
        / "icc.csv",
        index=False,
    )

    print()
    print("=" * 70)
    print("CEILING DISTRIBUTION")
    print("=" * 70)

    ceiling = ceiling_statistics(
        eval1,
        eval2,
    )

    print(
        ceiling.round(3).to_string(
            index=False
        )
    )

    ceiling.to_csv(
        args.output_dir
        / "ceiling_statistics.csv",
        index=False,
    )

    r, p = pearsonr(
        df["overall_e1"],
        df["overall_e2"],
    )

    print()
    print("=" * 70)
    print("OVERALL EVALUATOR CORRELATION")
    print("=" * 70)
    print(
        f"Pearson r = {r:.3f}, "
        f"p = {p:.6f}"
    )

    df.to_csv(
        args.output_dir
        / "artifact_level_analysis_dataset.csv",
        index=False,
    )

    print()
    print(
        f"Analysis files saved to: "
        f"{args.output_dir}"
    )


if __name__ == "__main__":
    main()
