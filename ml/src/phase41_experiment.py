"""Temporary Phase 4.1 validation/test experiment runner.

The Phase 4 test split is reconstructed exactly. Candidate and blend selection
uses train/validation only; ``--stage test`` evaluates frozen representatives.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd
from catboost import CatBoostRegressor
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import ExtraTreesRegressor, RandomForestRegressor
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.metrics import (
    mean_absolute_error,
    mean_absolute_percentage_error,
    mean_squared_error,
    median_absolute_error,
    r2_score,
)
from sklearn.model_selection import GroupKFold, GroupShuffleSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "raw" / "maisonlux_maroc_complet.csv"
RESULTS = ROOT / "ml" / "artifacts" / "phase41_experiments.json"
SEED = 42
EXPECTED_TEST_SHA256 = "b0d93a4cf01845a0fead2233a53bcfeb2b12c1ae37b58bb3fa0b99954d9eecdc"


def ascii_text(value: object) -> str:
    text = "" if pd.isna(value) else str(value).casefold()
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", text).strip()


def parse_price(value: object) -> float:
    text = ascii_text(value)
    if not text or "consulter" in text or "projet" in text:
        return np.nan
    digits = re.sub(r"[^0-9]", "", text.replace("a partir de", ""))
    if not digits:
        return np.nan
    price = float(digits)
    return price * 10.8 if "eur" in text else price


def split_location(series: pd.Series) -> tuple[pd.Series, pd.Series]:
    parts = series.astype("string").str.split(",", n=1, expand=True)
    first = parts[0].fillna("").str.strip()
    if parts.shape[1] == 1:
        return pd.Series("Non renseigné", index=series.index), first
    second = parts[1].fillna("").str.strip()
    has_comma = second.ne("")
    return first.where(has_comma, "Non renseigné"), second.where(has_comma, first)


def keyword(text: pd.Series, pattern: str) -> pd.Series:
    return text.str.contains(pattern, regex=True, na=False).astype(int)


def prepare(raw: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    audit = {"raw_rows": int(len(raw)), "exact_duplicates": int(raw.duplicated().sum())}
    df = raw.drop_duplicates().copy()
    df["Prix_num"] = df["Prix"].map(parse_price)
    df["Quartier"], df["Ville"] = split_location(df["Localisation"])
    df["Quartier"] = df["Quartier"].fillna("Non renseigné").str.strip()
    df["Ville"] = df["Ville"].fillna("Non renseigné").str.strip()
    title_original = df["Titre"].astype("string").fillna("").str.casefold()
    details_original = df["Details"].astype("string")
    title = df["Titre"].fillna("").map(ascii_text)
    details = df["Details"].fillna("").map(ascii_text)
    combined = title + " " + details
    # These four expressions deliberately match Phase 4 exactly so membership and indices stay frozen.
    df["Surface_m2"] = pd.to_numeric(details_original.str.extract(r"(\d+)\s*m²", expand=False), errors="coerce")
    df["Pieces"] = pd.to_numeric(details_original.str.extract(r"(\d+)\s*Pièce", expand=False), errors="coerce")
    df["Chambres"] = pd.to_numeric(details_original.str.extract(r"(\d+)\s*Ch", expand=False), errors="coerce")
    df["Salles_Bain"] = pd.to_numeric(details_original.str.extract(r"(\d+)\s*Salle", expand=False), errors="coerce")
    type_patterns = ["studio", "duplex", "villa", "maison", "appartement"]
    type_names = ["studio", "duplex", "villa", "maison", "appartement"]
    df["Type_Bien"] = np.select([title_original.str.contains(p, regex=False) for p in type_patterns], type_names, default="inconnu")

    df["Is_Haut_Standing"] = keyword(combined, r"haut standing|luxe|luxueux|prestig|exception")
    df["En_Construction"] = keyword(combined, r"en cours de construction|livraison\s*:")
    feature_patterns = {
        "Ascenseur": r"ascenseur", "Parking": r"parking|garage|place de voiture",
        "Terrasse": r"terrasse|rooftop|roof top", "Balcon": r"balcon",
        "Jardin": r"jardin|rez de jardin", "Piscine": r"piscine",
        "Meuble": r"meubl[ée]|furnished", "Renove": r"renov[ée]|refait a neuf",
        "Neuf": r"\bneuf\b|nouvelle construction|premiere main|jamais habite|finalise",
        "A_Renover": r"a renover|travaux a prevoir", "Securite": r"securis|securite|surveillance",
        "Concierge": r"concierge|gardien", "Vue_Mer": r"vue mer|front de mer|bord de mer|pieds dans l'eau",
        "Vue_Montagne": r"vue montagne|atlas", "Titre_Foncier": r"titre foncier|titre|melkia",
        "Proximite": r"proche|proximite|a deux pas|minutes? de|pres de",
        "RDC": r"\brdc\b|rez de chaussee|rez-de-chaussee", "Triplex": r"triplex",
        "Commercial": r"commercial|bureau|magasin", "Residentiel": r"residentiel|residence",
        "Climatise": r"climatis|air conditionne", "Cheminee": r"cheminee",
        "Cuisine_Equipee": r"cuisine equipee", "Double_Vitrage": r"double vitrage",
    }
    for name, pattern in feature_patterns.items():
        df[name] = keyword(combined, pattern)
    df["Etage"] = pd.to_numeric(
        combined.str.extract(r"(?:au|du|de|-)\s*(\d{1,2})(?:er|e|eme)?\s*etage", expand=False),
        errors="coerce",
    )
    df.loc[df["RDC"].eq(1), "Etage"] = 0
    df["Surface_Titre_m2"] = pd.to_numeric(title.str.extract(r"(\d{2,4})\s*m[2²]", expand=False), errors="coerce")
    df["Amenity_Count"] = df[list(feature_patterns)].sum(axis=1)
    luxury = ["Is_Haut_Standing", "Piscine", "Jardin", "Vue_Mer", "Concierge", "Securite", "Terrasse"]
    df["Luxury_Count"] = df[luxury].sum(axis=1)
    df["Condition_Score"] = 2 * df["Neuf"] + df["Renove"] - 2 * df["A_Renover"]
    df["Location_Complete"] = (df["Quartier"].ne("Non renseigné") & df["Ville"].ne("Non renseigné")).astype(int)
    df["Ville_Quartier"] = df["Ville"] + "__" + df["Quartier"]
    df["Ville_Type"] = df["Ville"] + "__" + df["Type_Bien"]
    df["Quartier_Type"] = df["Quartier"] + "__" + df["Type_Bien"]
    # Remove every digit and monetary cue so TF-IDF cannot reconstruct the label or structured numbers.
    clean_text = combined.str.replace(r"\b(?:prix|dh|dhs|mad|eur|million|millions)\b", " ", regex=True)
    df["Texte_Sans_Nombres"] = clean_text.str.replace(r"\d+", " ", regex=True).str.replace(r"\s+", " ", regex=True).str.strip()

    audit["unusable_price"] = int(df["Prix_num"].isna().sum())
    df = df[df["Prix_num"].notna()].copy()
    audit["unknown_type"] = int(df["Type_Bien"].eq("inconnu").sum())
    df = df[df["Type_Bien"].ne("inconnu")].copy()
    valid = (
        df["Surface_m2"].between(15, 1000)
        & (df["Pieces"].isna() | df["Pieces"].between(1, 15))
        & (df["Chambres"].isna() | df["Chambres"].between(0, 10))
        & (df["Salles_Bain"].isna() | df["Salles_Bain"].between(0, 10))
    )
    audit["invalid_input"] = int((~valid).sum())
    df = df[valid].copy()
    rental = title_original.loc[df.index].str.contains(
        r"\b(?:louer|location|à louer|a louer|en location|locations)\b", regex=True
    )
    audit["explicit_rental"] = int(rental.sum())
    df = df[~rental].copy()
    df["Prix_m2_audit"] = df["Prix_num"] / df["Surface_m2"]
    plausible = df["Prix_m2_audit"].between(1000, 150000)
    audit["implausible_ppm2"] = int((~plausible).sum())
    df = df[plausible].copy()

    def phase4_normalize(series: pd.Series) -> pd.Series:
        clean = series.astype("string").fillna("").str.replace(r"\s+", " ", regex=True).str.strip()
        return clean.mask(clean.eq(""), "Non renseigné")

    exact_signature = (
        phase4_normalize(df["Titre"]).str.casefold() + "|"
        + phase4_normalize(df["Localisation"]).str.casefold() + "|"
        + phase4_normalize(df["Details"]).str.casefold()
    )
    df["Listing_Group"] = pd.util.hash_pandas_object(exact_signature, index=False).astype("uint64").astype(str)
    # Conservative near-duplicate fingerprint: title words (no digits) + location + core facts.
    title_signature = title.loc[df.index].str.replace(r"\d+", " ", regex=True).str.replace(r"\W+", " ", regex=True).str.strip()
    facts = (
        df["Ville"].map(ascii_text) + "|" + df["Quartier"].map(ascii_text) + "|" + title_signature
        + "|" + df["Surface_m2"].fillna(-1).round().astype(str)
        + "|" + df["Pieces"].fillna(-1).astype(str) + "|" + df["Type_Bien"]
    )
    df["Near_Group"] = pd.util.hash_pandas_object(facts, index=False).astype("uint64").astype(str)
    audit["modeling_rows"] = int(len(df))
    audit["attribute_counts"] = {c: int(df[c].sum()) for c in feature_patterns}
    audit["floor_observed"] = int(df["Etage"].notna().sum())
    audit["title_surface_observed"] = int(df["Surface_Titre_m2"].notna().sum())
    return df, audit


BASE_NUM = ["Surface_m2", "Pieces", "Chambres", "Salles_Bain", "Is_Haut_Standing", "En_Construction"]
RICH_NUM = BASE_NUM + [
    "Ascenseur", "Parking", "Terrasse", "Balcon", "Jardin", "Piscine", "Meuble", "Renove", "Neuf",
    "A_Renover", "Securite", "Concierge", "Vue_Mer", "Vue_Montagne", "Titre_Foncier", "Proximite",
    "RDC", "Triplex", "Commercial", "Residentiel", "Climatise", "Cheminee", "Cuisine_Equipee",
    "Double_Vitrage", "Etage", "Surface_Titre_m2", "Amenity_Count", "Luxury_Count", "Condition_Score",
    "Location_Complete",
]
BASE_CAT = ["Type_Bien", "Ville", "Quartier"]
RICH_CAT = BASE_CAT + ["Ville_Quartier", "Ville_Type", "Quartier_Type"]


def add_ratios(frame: pd.DataFrame, rich: bool) -> pd.DataFrame:
    cols = (RICH_NUM if rich else BASE_NUM) + (RICH_CAT if rich else BASE_CAT)
    out = frame[cols].copy()
    out["Surface_Par_Piece"] = out["Surface_m2"] / out["Pieces"].clip(lower=1)
    out["Surface_Par_Chambre"] = out["Surface_m2"] / out["Chambres"].clip(lower=1)
    out["Pieces_100m2"] = out["Pieces"] * 100 / out["Surface_m2"]
    out["Bains_Par_Chambre"] = out["Salles_Bain"] / out["Chambres"].clip(lower=1)
    out["Ratio_Chambre"] = out["Chambres"] / out["Pieces"].clip(lower=1)
    out["Difference_Pieces"] = out["Pieces"] - out["Chambres"]
    out["Surface_Type"] = out["Surface_m2"].round(-1).astype("Int64").astype("string") + "__" + out["Type_Bien"]
    return out


def cat_frame(frame: pd.DataFrame, rich: bool) -> tuple[pd.DataFrame, list[str]]:
    out = add_ratios(frame, rich)
    cat_cols = (RICH_CAT if rich else BASE_CAT) + ["Surface_Type"]
    for col in cat_cols:
        out[col] = out[col].astype("string").fillna("Non renseigne")
    for col in out.columns.difference(cat_cols):
        median = frame[col].median() if col in frame and frame[col].notna().any() else 0
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(median)
        out[col] = out[col].fillna(0)
    return out, cat_cols


def metrics(y, pred) -> dict:
    return {
        "r2": float(r2_score(y, pred)), "mae": float(mean_absolute_error(y, pred)),
        "rmse": float(mean_squared_error(y, pred) ** 0.5),
        "median_ae": float(median_absolute_error(y, pred)),
        "mape_percent": float(mean_absolute_percentage_error(y, pred) * 100),
    }


def make_cat(params: dict, loss: str = "RMSE") -> CatBoostRegressor:
    return CatBoostRegressor(
        random_seed=SEED, verbose=False, allow_writing_files=False, thread_count=-1,
        loss_function=loss, **params,
    )


def fit_cat(train, evaluation, rich, params, log_target=False):
    xtr, cats = cat_frame(train, rich); xev, _ = cat_frame(evaluation, rich)
    ytr = np.log1p(train.Prix_num) if log_target else train.Prix_num
    model = make_cat(params)
    model.fit(xtr, ytr, cat_features=cats)
    pred = model.predict(xev)
    return model, np.expm1(pred) if log_target else pred


def text_model(train, evaluation, alpha=30.0):
    structured_num = BASE_NUM
    structured_cat = BASE_CAT
    prep = ColumnTransformer([
        ("num", Pipeline([("imp", SimpleImputer(strategy="median", add_indicator=True)), ("scale", StandardScaler())]), structured_num),
        ("cat", OneHotEncoder(handle_unknown="infrequent_if_exist", min_frequency=8), structured_cat),
        ("text", TfidfVectorizer(min_df=3, max_df=.98, ngram_range=(1, 2), max_features=25000, sublinear_tf=True), "Texte_Sans_Nombres"),
    ])
    model = Pipeline([("prep", prep), ("ridge", Ridge(alpha=alpha))])
    model.fit(train, train.Prix_num)
    return model, model.predict(evaluation)


def split_data(df: pd.DataFrame):
    split_test = GroupShuffleSplit(n_splits=1, test_size=.15, random_state=42)
    tv_idx, test_idx = next(split_test.split(df, groups=df.Listing_Group))
    tv, test = df.iloc[tv_idx].copy(), df.iloc[test_idx].copy()
    split_val = GroupShuffleSplit(n_splits=1, test_size=.1764705882, random_state=43)
    tr_idx, va_idx = next(split_val.split(tv, groups=tv.Listing_Group))
    train, val = tv.iloc[tr_idx].copy(), tv.iloc[va_idx].copy()
    # Keep every fixed test row; quarantine train/validation rows that match its conservative near-group.
    test_near = set(test.Near_Group)
    train_collision = train.Near_Group.isin(test_near)
    val_collision = val.Near_Group.isin(test_near)
    quarantine = {"train": int(train_collision.sum()), "validation": int(val_collision.sum())}
    return train[~train_collision].copy(), val[~val_collision].copy(), test, quarantine


CAT_CONFIGS = {
    "cat_base_raw_d6": ({"iterations": 700, "depth": 6, "learning_rate": .05, "l2_leaf_reg": 5}, False, False),
    "cat_base_raw_d8": ({"iterations": 800, "depth": 8, "learning_rate": .04, "l2_leaf_reg": 8}, False, False),
    "cat_base_log_d7": ({"iterations": 750, "depth": 7, "learning_rate": .05, "l2_leaf_reg": 6}, False, True),
    "cat_rich_raw_d6": ({"iterations": 800, "depth": 6, "learning_rate": .045, "l2_leaf_reg": 6}, True, False),
    "cat_rich_raw_d8": ({"iterations": 900, "depth": 8, "learning_rate": .035, "l2_leaf_reg": 10}, True, False),
    "cat_rich_log_d7": ({"iterations": 800, "depth": 7, "learning_rate": .045, "l2_leaf_reg": 8}, True, True),
}


def validation_stage(train, val, audit, quarantine):
    rows, predictions = {}, {}
    for name, (params, rich, log_target) in CAT_CONFIGS.items():
        _, pred = fit_cat(train, val, rich, params, log_target)
        predictions[name] = pred
        rows[name] = metrics(val.Prix_num, pred)
        print(name, rows[name], flush=True)
    for alpha in [10., 30., 100.]:
        name = f"tfidf_structured_ridge_a{int(alpha)}"
        _, pred = text_model(train, val, alpha)
        predictions[name] = pred; rows[name] = metrics(val.Prix_num, pred)
        print(name, rows[name], flush=True)

    # Segment and city specialists: global rich CatBoost plus local models where train support is adequate.
    global_params = CAT_CONFIGS["cat_rich_raw_d6"][0]
    global_model, global_pred = fit_cat(train, val, True, global_params, False)
    for architecture, column, minimum in [("type_segmented", "Type_Bien", 300), ("city_segmented", "Ville", 500)]:
        pred = global_pred.copy()
        used = {}
        for segment, count in train[column].value_counts().items():
            if count < minimum:
                continue
            tr = train[train[column].eq(segment)]; mask = val[column].eq(segment)
            if mask.sum() < 20:
                continue
            local, lp = fit_cat(tr, val[mask], True, {"iterations": 500, "depth": 6, "learning_rate": .05, "l2_leaf_reg": 8}, False)
            pred[np.flatnonzero(mask.to_numpy())] = lp
            used[str(segment)] = {"train": int(count), "validation": int(mask.sum())}
        predictions[architecture] = pred
        rows[architecture] = {**metrics(val.Prix_num, pred), "specialists": used}
        print(architecture, rows[architecture], flush=True)

    # Blend weights are selected only on validation.
    cat_name = min(CAT_CONFIGS, key=lambda n: rows[n]["mae"])
    text_name = min((n for n in rows if n.startswith("tfidf")), key=lambda n: rows[n]["mae"])
    blend_search = []
    for text_weight in np.arange(0, .55, .05):
        pred = (1-text_weight) * predictions[cat_name] + text_weight * predictions[text_name]
        blend_search.append({"text_weight": float(text_weight), **metrics(val.Prix_num, pred)})
    best_blend = min(blend_search, key=lambda x: x["mae"])
    payload = {
        "audit": audit, "quarantine": quarantine, "split": {"train": len(train), "validation": len(val), "test": 1844},
        "validation": rows, "selected_cat": cat_name, "selected_text": text_name,
        "blend_search": blend_search, "selected_text_weight": best_blend["text_weight"],
    }
    RESULTS.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print("SELECTED", cat_name, text_name, best_blend, flush=True)


def cv_stage(train):
    prior = json.loads(RESULTS.read_text(encoding="utf-8"))
    name = prior["selected_cat"]
    params, rich, log_target = CAT_CONFIGS[name]
    folds = []
    splitter = GroupKFold(n_splits=3)
    for fold, (fit_idx, score_idx) in enumerate(splitter.split(train, groups=train.Listing_Group), start=1):
        _, pred = fit_cat(train.iloc[fit_idx], train.iloc[score_idx], rich, params, log_target)
        result = {"fold": fold, **metrics(train.iloc[score_idx].Prix_num, pred)}
        folds.append(result); print("CV", result, flush=True)
    prior["grouped_cv"] = {
        "model": name, "folds": folds,
        "mean_r2": float(np.mean([x["r2"] for x in folds])),
        "std_r2": float(np.std([x["r2"] for x in folds])),
        "mean_mae": float(np.mean([x["mae"] for x in folds])),
        "mean_rmse": float(np.mean([x["rmse"] for x in folds])),
    }
    RESULTS.write_text(json.dumps(prior, ensure_ascii=False, indent=2), encoding="utf-8")
    print("CV SUMMARY", prior["grouped_cv"], flush=True)


def test_stage(train, val, test, audit, quarantine):
    prior = json.loads(RESULTS.read_text(encoding="utf-8"))
    train_val = pd.concat([train, val]).sort_index()
    names = ["cat_base_raw_d6", "cat_base_log_d7", "cat_rich_raw_d6", "cat_rich_log_d7", prior["selected_cat"]]
    rows, preds = {}, {}
    for name in dict.fromkeys(names):
        params, rich, log_target = CAT_CONFIGS[name]
        _, pred = fit_cat(train_val, test, rich, params, log_target)
        preds[name] = pred; rows[name] = metrics(test.Prix_num, pred)
        print(name, rows[name], flush=True)
    alpha = float(prior["selected_text"].split("a")[-1])
    _, text_pred = text_model(train_val, test, alpha)
    preds[prior["selected_text"]] = text_pred
    rows[prior["selected_text"]] = metrics(test.Prix_num, text_pred)

    # Predeclared segmented architectures, evaluated once on the fixed test.
    global_name = "cat_rich_raw_d6"; global_pred = preds[global_name]
    for architecture, column, minimum in [("type_segmented", "Type_Bien", 300), ("city_segmented", "Ville", 500)]:
        pred = global_pred.copy(); used = {}
        for segment, count in train_val[column].value_counts().items():
            if count < minimum:
                continue
            mask = test[column].eq(segment)
            if mask.sum() < 20:
                continue
            _, lp = fit_cat(train_val[train_val[column].eq(segment)], test[mask], True,
                            {"iterations": 500, "depth": 6, "learning_rate": .05, "l2_leaf_reg": 8}, False)
            pred[np.flatnonzero(mask.to_numpy())] = lp
            used[str(segment)] = {"train_validation": int(count), "test": int(mask.sum())}
        preds[architecture] = pred; rows[architecture] = {**metrics(test.Prix_num, pred), "specialists": used}
        print(architecture, rows[architecture], flush=True)

    weight = prior["selected_text_weight"]
    blend = (1-weight) * preds[prior["selected_cat"]] + weight * text_pred
    rows["validation_selected_blend"] = {**metrics(test.Prix_num, blend), "text_weight": weight}
    print("validation_selected_blend", rows["validation_selected_blend"], flush=True)
    prior["test"] = rows
    prior["test_target_summary"] = {
        "n": len(test), "min": float(test.Prix_num.min()), "median": float(test.Prix_num.median()),
        "max": float(test.Prix_num.max()), "luxury_over_5m": int(test.Prix_num.gt(5_000_000).sum()),
    }
    RESULTS.write_text(json.dumps(prior, ensure_ascii=False, indent=2), encoding="utf-8")


def analysis_stage(train, val, test):
    """Post-test diagnostics only; no model/weight selection happens here."""
    prior = json.loads(RESULTS.read_text(encoding="utf-8"))
    train_val = pd.concat([train, val]).sort_index()
    selected = prior["selected_cat"]
    params, rich, log_target = CAT_CONFIGS[selected]
    _, cat_pred = fit_cat(train_val, test, rich, params, log_target)
    alpha = float(prior["selected_text"].split("a")[-1])
    _, text_pred = text_model(train_val, test, alpha)
    weight = prior["selected_text_weight"]
    pred = (1-weight) * cat_pred + weight * text_pred
    result = test[["Titre", "Ville", "Quartier", "Type_Bien", "Surface_m2", "Prix_num",
                   "Amenity_Count", "Luxury_Count", "Vue_Mer", "Piscine", "Jardin"]].copy()
    result["Prediction"] = pred
    result["Abs_Error"] = (result.Prix_num - result.Prediction).abs()
    result["Squared_Error"] = (result.Prix_num - result.Prediction) ** 2

    def segments(column, minimum=20):
        output = {}
        for name, part in result.groupby(column, observed=True):
            if len(part) >= minimum:
                output[str(name)] = {"n": len(part), **metrics(part.Prix_num, part.Prediction)}
        return output

    result["Price_Band"] = pd.cut(result.Prix_num, [-np.inf, 1e6, 2e6, 5e6, np.inf],
                                  labels=["low_<=1m", "mid_1m_2m", "upper_2m_5m", "luxury_>5m"])
    result["Surface_Band"] = pd.cut(result.Surface_m2, [0, 60, 100, 150, 250, np.inf],
                                    labels=["<=60", "60_100", "100_150", "150_250", ">250"])
    top_n = max(1, int(np.ceil(len(result) * .01)))
    total_sse = result.Squared_Error.sum()
    worst = result.nlargest(15, "Abs_Error")

    # Quantify contradictory labels for observations indistinguishable to the current API.
    observable_cols = BASE_NUM + BASE_CAT
    observable = pd.concat([train_val, test])
    keys = observable[observable_cols].copy()
    for col in BASE_NUM:
        keys[col] = keys[col].fillna(-1).round(2)
    for col in BASE_CAT:
        keys[col] = keys[col].fillna("Non renseigné").map(ascii_text)
    observable_group = pd.util.hash_pandas_object(keys.astype(str).agg("|".join, axis=1), index=False)
    ambiguity = pd.DataFrame({"group": observable_group.to_numpy(), "price": observable.Prix_num.to_numpy()})
    group_stats = ambiguity.groupby("group").price.agg(["size", "min", "max", "mean", "var"])
    repeated = group_stats[group_stats["size"].ge(2)].copy()
    conflicting = repeated[repeated["max"].div(repeated["min"]).gt(1.5)]

    diagnostics = {
        "best_offline_metrics": metrics(result.Prix_num, result.Prediction),
        "price_bands": segments("Price_Band", 1), "surface_bands": segments("Surface_Band", 1),
        "property_types": segments("Type_Bien", 20), "cities": segments("Ville", 20),
        "error_concentration": {
            "top_1pct_n": top_n,
            "top_1pct_sse_share_percent": float(result.nlargest(top_n, "Squared_Error").Squared_Error.sum() / total_sse * 100),
            "luxury_sse_share_percent": float(result[result.Prix_num.gt(5_000_000)].Squared_Error.sum() / total_sse * 100),
        },
        "observable_label_ambiguity": {
            "repeated_observable_groups": int(len(repeated)),
            "rows_in_repeated_observable_groups": int(repeated["size"].sum()),
            "groups_with_price_ratio_over_1_5": int(len(conflicting)),
            "rows_in_conflicting_groups": int(conflicting["size"].sum()),
        },
        "largest_errors": worst[["Titre", "Ville", "Quartier", "Type_Bien", "Surface_m2", "Prix_num", "Prediction", "Abs_Error"]].to_dict("records"),
    }

    # Learning curve on validation only, with a fixed nested sample of training groups.
    rng = np.random.default_rng(SEED)
    groups = train.Listing_Group.unique().copy(); rng.shuffle(groups)
    curve = []
    base_params = {"iterations": 500, "depth": 7, "learning_rate": .05, "l2_leaf_reg": 6}
    for fraction in [.25, .50, .75, 1.0]:
        keep = set(groups[:max(1, int(len(groups) * fraction))])
        subset = train[train.Listing_Group.isin(keep)]
        _, lp = fit_cat(subset, val, False, base_params, True)
        curve.append({"fraction": fraction, "n_train": len(subset), **metrics(val.Prix_num, lp)})
        print("LEARNING", curve[-1], flush=True)
    diagnostics["learning_curve_validation"] = curve
    prior["diagnostics"] = diagnostics
    RESULTS.write_text(json.dumps(prior, ensure_ascii=False, indent=2), encoding="utf-8")
    print("DIAGNOSTICS", json.dumps(diagnostics, ensure_ascii=False), flush=True)


def manifest_stage(test):
    prior = json.loads(RESULTS.read_text(encoding="utf-8"))
    records = [{"raw_index": int(index), "listing_group": str(group)}
               for index, group in zip(test.index, test.Listing_Group)]
    canonical = "\n".join(f"{row['raw_index']}|{row['listing_group']}" for row in records)
    prior["fixed_test_manifest"] = {
        "n": len(records), "sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "records": records,
    }
    RESULTS.write_text(json.dumps(prior, ensure_ascii=False, indent=2), encoding="utf-8")
    print("MANIFEST", prior["fixed_test_manifest"]["n"], prior["fixed_test_manifest"]["sha256"])


def main():
    parser = argparse.ArgumentParser(); parser.add_argument(
        "--stage", choices=["validation", "cv", "test", "analysis", "manifest"], default="validation"
    )
    args = parser.parse_args()
    df, audit = prepare(pd.read_csv(DATA))
    train, val, test, quarantine = split_data(df)
    canonical = "\n".join(f"{int(index)}|{group}" for index, group in zip(test.index, test.Listing_Group))
    split_sha = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    if len(df) != 12267 or len(test) != 1844 or split_sha != EXPECTED_TEST_SHA256:
        raise RuntimeError("La cohorte ou le test Phase 4 a changé : évaluation arrêtée.")
    print("SPLIT", len(train), len(val), len(test), "QUARANTINE", quarantine, flush=True)
    if args.stage == "validation": validation_stage(train, val, audit, quarantine)
    elif args.stage == "cv": cv_stage(train)
    elif args.stage == "test": test_stage(train, val, test, audit, quarantine)
    elif args.stage == "analysis": analysis_stage(train, val, test)
    else: manifest_stage(test)


if __name__ == "__main__":
    main()
