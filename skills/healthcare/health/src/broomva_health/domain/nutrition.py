"""Nutrition domain: foods, meal items and meal totals.

Values are per 100 g of edible food, as food-composition tables publish them.
A meal is a list of items, each a food from the local table and a mass in grams.
Totals are the sum of every item scaled to its mass.

Every meal estimate carries an uncertainty band. Photo-based estimates of a
single meal are off by roughly a third (multimodal models: about 36% mean
absolute percentage error on energy; photo apps: about 33% under on energy and
about 30 g under on fat against weighed meals), and most of the error is portion
size and ingredients a photo cannot show, such as cooking oil and sugar. Items
the eater did not see but the dish usually contains are marked ``hidden``, so a
reader can tell them from what was on the plate.
"""

from __future__ import annotations

import re
from datetime import date, time
from typing import Final

from pydantic import BaseModel, ConfigDict, Field, field_validator

__all__ = [
    "MEAL_KINDS",
    "UNCERTAINTY",
    "Food",
    "Meal",
    "MealItem",
    "Nutrients",
    "parse_item_spec",
]

#: Relative half-width of the band reported around a meal's totals.
UNCERTAINTY: Final[float] = 0.30

MEAL_KINDS: Final[tuple[str, ...]] = (
    "breakfast",
    "lunch",
    "dinner",
    "snack",
    "pre-workout",
    "post-workout",
    "drink",
)

_FOOD_ID = re.compile(r"^[a-z0-9_-]+:[A-Za-z0-9_.-]+$")
_MAX_GRAMS: Final[float] = 5000.0


class Nutrients(BaseModel):
    """Energy and macronutrients for some mass of food. ``None`` means not reported."""

    model_config = ConfigDict(frozen=True)

    kcal: float | None = None
    protein_g: float | None = None
    fat_g: float | None = None
    carbs_g: float | None = None
    fiber_g: float | None = None
    sugars_g: float | None = None

    @field_validator("*")
    @classmethod
    def _non_negative(cls, value: float | None) -> float | None:
        if value is not None and value < 0:
            raise ValueError("nutrient amounts cannot be negative")
        return value

    def scaled(self, grams: float) -> Nutrients:
        """This per-100 g profile scaled to ``grams`` of food."""
        factor = grams / 100.0
        return Nutrients(
            **{k: None if v is None else round(v * factor, 2) for k, v in self.model_dump().items()}
        )

    def __add__(self, other: Nutrients) -> Nutrients:
        merged: dict[str, float | None] = {}
        for key, mine in self.model_dump().items():
            theirs = getattr(other, key)
            if mine is None and theirs is None:
                merged[key] = None
            else:
                merged[key] = round((mine or 0.0) + (theirs or 0.0), 2)
        return Nutrients(**merged)

    def band(self, uncertainty: float = UNCERTAINTY) -> tuple[Nutrients, Nutrients]:
        """(low, high) bounds at ``±uncertainty`` around these totals."""
        low = {
            k: None if v is None else round(v * (1 - uncertainty), 1)
            for k, v in self.model_dump().items()
        }
        high = {
            k: None if v is None else round(v * (1 + uncertainty), 1)
            for k, v in self.model_dump().items()
        }
        return Nutrients(**low), Nutrients(**high)


class Food(BaseModel):
    """One entry of a food-composition table. ``per_100g`` is per 100 g edible portion."""

    model_config = ConfigDict(frozen=True)

    food_id: str
    source: str
    description: str
    per_100g: Nutrients

    @field_validator("food_id")
    @classmethod
    def _valid_id(cls, value: str) -> str:
        if not _FOOD_ID.match(value):
            raise ValueError(f"food id must look like 'source:id', got {value!r}")
        return value


class MealItem(BaseModel):
    """One food in a meal with its estimated mass."""

    model_config = ConfigDict(frozen=True)

    food_id: str
    description: str
    grams: float = Field(gt=0, le=_MAX_GRAMS)
    hidden: bool = False
    nutrients: Nutrients

    @classmethod
    def of(cls, food: Food, grams: float, *, hidden: bool = False) -> MealItem:
        return cls(
            food_id=food.food_id,
            description=food.description,
            grams=grams,
            hidden=hidden,
            nutrients=food.per_100g.scaled(grams),
        )


class Meal(BaseModel):
    """A logged meal: when, what kind, its items, totals and the uncertainty band."""

    day: date
    at: time | None = None
    kind: str | None = None
    items: list[MealItem]
    totals: Nutrients
    low: Nutrients
    high: Nutrients
    uncertainty: float = UNCERTAINTY
    note: str | None = None
    photo: str | None = None

    @field_validator("kind")
    @classmethod
    def _known_kind(cls, value: str | None) -> str | None:
        if value is not None and value not in MEAL_KINDS:
            raise ValueError(f"meal kind must be one of {MEAL_KINDS}, got {value!r}")
        return value

    @classmethod
    def build(
        cls,
        items: list[MealItem],
        *,
        day: date,
        at: time | None = None,
        kind: str | None = None,
        note: str | None = None,
        photo: str | None = None,
        uncertainty: float = UNCERTAINTY,
    ) -> Meal:
        if not items:
            raise ValueError("a meal needs at least one item")
        totals = Nutrients()
        for item in items:
            totals = totals + item.nutrients
        low, high = totals.band(uncertainty)
        return cls(
            day=day,
            at=at,
            kind=kind,
            items=items,
            totals=totals,
            low=low,
            high=high,
            uncertainty=uncertainty,
            note=note,
            photo=photo,
        )


def parse_item_spec(spec: str) -> tuple[str, float, bool]:
    """Parse ``[+]SOURCE:ID=GRAMS`` into (food_id, grams, hidden).

    A leading ``+`` marks a hidden item (cooking oil, sugar, sauce) that the
    estimate adds because the dish usually contains it, not because it was seen.
    """
    raw = spec.strip()
    hidden = raw.startswith("+")
    if hidden:
        raw = raw[1:].strip()
    food_id, sep, grams_raw = raw.rpartition("=")
    if not sep or not food_id:
        raise ValueError(
            f"item must look like 'source:id=grams' (optionally '+' first), got {spec!r}"
        )
    if not _FOOD_ID.match(food_id):
        raise ValueError(f"food id must look like 'source:id', got {food_id!r}")
    try:
        grams = float(grams_raw)
    except ValueError as exc:
        raise ValueError(f"grams must be a number, got {grams_raw!r}") from exc
    if not 0 < grams <= _MAX_GRAMS:
        raise ValueError(f"grams must be above 0 and at most {_MAX_GRAMS:g}, got {grams:g}")
    return food_id, grams, hidden
