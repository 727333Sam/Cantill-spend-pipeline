from __future__ import annotations

import re

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import FeatureUnion


def normalize_text(value: object) -> str:
    text = re.sub(r"[^A-Za-z0-9]+", " ", str(value).lower())
    return re.sub(r"\s+", " ", text).strip()


class RuntimeTaxonomyClassifier:
    def __init__(self, taxonomy: pd.DataFrame, label_columns: list[str]):
        self.taxonomy = taxonomy
        self.label_columns = label_columns
        self.depth = len(label_columns)
        self.model = None
        self.vectorizer = None
        self.taxonomy_vectorizer = None
        self.taxonomy_vectors = None
        self.leaf_text = None

    def fit(self, frame: pd.DataFrame, text_column: str) -> None:
        required = [text_column] + self.label_columns
        frame = frame.dropna(subset=required)
        frame = frame.copy()
        frame["_text"] = frame[text_column].map(normalize_text)
        frame = frame[frame["_text"].str.len() > 0]
        if frame.empty:
            return
        frame["_leaf"] = frame[self.label_columns].astype(str).agg("|".join, axis=1)
        unique = frame["_leaf"].nunique()
        if unique < 2:
            return
        self.vectorizer = FeatureUnion([
            ("word", TfidfVectorizer(analyzer="word", ngram_range=(1, 2), min_df=1, sublinear_tf=True)),
            ("char", TfidfVectorizer(analyzer="char", ngram_range=(3, 5), min_df=1, sublinear_tf=True)),
        ])
        vectors = self.vectorizer.fit_transform(frame["_text"])
        self.model = LogisticRegression(max_iter=300, C=4.0)
        self.model.fit(vectors, frame["_leaf"])

    def build_taxonomy_fallback(self) -> None:
        rows = []
        leaves = []
        for _, row in self.taxonomy.iterrows():
            parts = [normalize_text(row.get(column, "")) for column in self.label_columns]
            parts = [part for part in parts if part]
            if parts:
                rows.append(" ".join(parts))
                leaves.append("|".join(str(row[column]) for column in self.label_columns if str(row.get(column, "")).strip()))
        if not rows:
            return
        self.taxonomy_vectorizer = TfidfVectorizer(analyzer="char", ngram_range=(3, 5), sublinear_tf=True)
        self.taxonomy_vectors = self.taxonomy_vectorizer.fit_transform(rows)
        self.leaf_text = leaves

    def predict(self, text: object) -> tuple[list[str], float]:
        cleaned = normalize_text(text)
        if not cleaned:
            return [""] * 4, 0.1
        if self.model is not None and self.vectorizer is not None:
            probabilities = self.model.predict_proba(self.vectorizer.transform([cleaned]))[0]
            leaf = str(self.model.classes_[int(np.argmax(probabilities))])
            parts = leaf.split("|")
            confidence = float(np.max(probabilities))
            while len(parts) < self.depth:
                parts.append("")
            parts = parts[:self.depth]
            while len(parts) < 4:
                parts.append("")
            return parts, min(1.0, max(0.0, confidence))
        if self.taxonomy_vectorizer is not None and self.taxonomy_vectors is not None:
            vector = self.taxonomy_vectorizer.transform([cleaned])
            scores = (vector @ self.taxonomy_vectors.T).toarray()[0]
            index = int(np.argmax(scores))
            leaf = self.leaf_text[index]
            parts = leaf.split("|")
            while len(parts) < self.depth:
                parts.append("")
            parts = parts[:self.depth]
            while len(parts) < 4:
                parts.append("")
            confidence = float(min(0.75, max(0.15, scores[index])))
            return parts, confidence
        return [""] * 4, 0.1
