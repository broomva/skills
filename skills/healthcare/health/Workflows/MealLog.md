# MealLog

**When invoked:** the user sends a meal photo or describes a meal ("lunch, rice and chicken"),
asks what they ate, or asks how food relates to their energy, sleep or training.

The skill keeps a **local food table** (USDA FoodData Central plus any regional table the user
adds) and a **private meal log** (`<data_dir>/meals.jsonl`, 0600). Nothing is uploaded: the
table is built from files the user downloaded, and photos are copied into
`<data_dir>/meal-photos/`. Do not send meal photos to a third-party calorie app.

## How accurate this is (say it when it matters)

- **A single meal is off by about a third.**
  - Multimodal models: ChatGPT-4o and Claude 3.5 Sonnet had about 36% mean absolute percentage error on energy; Gemini 1.5 Pro had 64–110% across nutrients. Every model underestimated more as portions grew (Fridolfsson et al., *Curr Dev Nutr* 2025, PMID 41081011).
  - Photo apps: about 33% under on energy and about 30 g under on fat, against weighed meals (NIH metabolic-kitchen test, 2026 conference report, not yet peer-reviewed; reported at https://www.healio.com/news/primary-care/20260804/ai-photobased-calorietracking-tools-underestimate-them-by-33).
- **Most of the error is portion size and what the photo can't show:** cooking oil, butter, sugar, sauces.
- **Trends are more reliable than any single meal.** Weekly averages, meal-to-meal comparisons, timing and protein per meal are worth reading. A single calorie number is not.
- If a food in the table lacks a value (some regional entries report no fibre or sugar), that nutrient's total is marked `partial`: it is a lower bound. Say so rather than reading it as the amount.
- Every logged meal carries a symmetric ±30% band (`low` / `high`). Report the range, not just the point. Photo estimates run low more often than high, especially for large portions, so the upper half of the band is the likelier one.

## One-time setup

1. Download the FoodData Central CSVs from https://fdc.nal.usda.gov/download-datasets:
   Foundation Foods and SR Legacy (about 10 MB zipped), optionally FNDDS. Unzip into one folder.
2. `health food import-usda <folder>`. The Oct 2026 Foundation + SR Legacy releases give about 8,300 foods. A folder with no importable foods is refused and leaves the table unchanged.
3. Optional: a regional table for staples USDA lacks or gets wrong.
   - Use a CSV with `food_id, description, kcal, protein_g, fat_g, carbs_g, fiber_g, sugars_g`, all per 100 g, taken from a published national table.
   - Import it with `health food import-csv staples.csv --source <xx>`.
   - Never type in numbers from memory: an invented value is worse than a missing one.

## Logging a meal (the decomposition)

Follow the Open-KNEAD recipe (Coburn et al., arXiv 2607.12911). For each meal:

1. **List what is visible**, one item at a time, each with grams.
   - Use whatever gives scale: a fork, a hand, the plate, a card.
   - Ask about portion only if the photo can't settle it and the answer would change the picture.
   - The user's own words win ("2 eggs", "a cup of rice").
2. **Add what the dish usually contains but the photo can't show** (the "recipe prior"), as hidden items marked with a leading `+`:
   - oil for anything fried or sautéed
   - sugar in coffee, juice or *aguapanela*
   - butter on bread
   - dressing on salad

   Skip this for whole fruit, plain salads and anything the user says was cooked dry.
3. **Find each food**, e.g. `health food find "rice white cooked"`.
   - Pick the closest match for how the food was prepared: cooked vs raw, fried vs boiled. These differ two- to five-fold per 100 g.
4. **Log it:**

   ```bash
   health food log --meal lunch --at 13:10 --photo ~/path/IMG.jpg \
     --item usda:168880=180 --item usda:171477=120 --item +usda:171413=10 \
     --note "felt heavy after"
   ```

5. **Reply in one line.** Give what was logged, the energy range and protein, and one useful observation if there is one:
   - nothing eaten in the 60–90 min before training
   - caffeine after mid-afternoon
   - a very large late meal

   No judgement, and no running calorie budget unless the user asked for one.

## Photo tips to give the user once

- Shoot at about 45° with a fork or hand in frame. Add a top-down shot for a full plate.
- Say what the camera can't see: "fried", "two sugars", "with sauce".
- Take an after-photo if a lot is left over.
- For packaged food, photograph the label.
- Weighing usual portions for a week (the rice bowl, the arepa) turns the biggest guess into a measurement.

## Reading it back

- `health food show --days 7`: one row per meal, with items, totals and energy range.
- `health food show --days 7 --totals`: one row per day.
- Pair meals with traces for questions that matter:
  - an afternoon energy dip vs lunch size and timing
  - body battery and HRV vs late meals or alcohol
  - training days vs carbohydrate before the session
  - fibre vs digestion notes

  Correlations over a few weeks are observational; say so.

## Example output

```
date        at     meal   items                                                     kcal   protein_g  kcal_range
2026-01-12  13:10  lunch  Rice, white, cooked 180 g; Chicken breast, roasted 120 g;  520.4  41.5       364-676
                          +Oil, olive 10 g
```

## If the food table cannot be read

- Copy `foods.db` aside before doing anything else. It holds every imported source, USDA and the user's own CSVs, and the meal log is a separate file it never touches.
- To start again, run `health food import-usda` and the `import-csv` commands again: they build a new table.

## Out of scope

- Medical nutrition therapy, allergies and diabetes dosing: a clinician.
- Micronutrients: the food table stores only energy, protein, fat, carbohydrate, fibre and sugars.
