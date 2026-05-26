# alkosto-wait-optimizer (skills.sh)

Skill para estimar tiempo de espera optimo en la promo de Alkosto usando dos metodos:

- `purchase_rate`: cuentas compras cerradas por minuto.
- `winner_timestamps`: solo escuchas anuncios de ganadores y registras timestamps.

## Alcance

- Lunes a viernes: cada 25 clientes.
- Sabado, domingo y festivo: cada 50 clientes.
- Alkosto no publica un tiempo promedio oficial; este skill entrega un estimado operativo.

## Estructura

- `SKILL.md`: skill instalable por `npx skills add`.
- `scripts/calc_wait.py`: calculadora deterministica para ejecutar por terminal.
- `skill.json` + `index.ts`: implementacion TypeScript para runtimes compatibles con ese formato.

## Ejemplo 1: por flujo de compras

```bash
python3 scripts/calc_wait.py --pretty --input-json '{
  "mode": "purchase_rate",
  "is_weekend_or_holiday": true,
  "model": "global",
  "observed_purchases": 5,
  "observed_minutes": 2,
  "observed_lanes": 5,
  "total_open_lanes": 15,
  "confidence_buffer": 0.2,
  "target_hit_probability": 0.75,
  "max_wait_minutes": 30
}'
```

## Ejemplo 2: por timestamps de ganadores

```bash
python3 scripts/calc_wait.py --pretty --input-json '{
  "mode": "winner_timestamps",
  "winner_timestamps": ["12:10:15", "12:27:40", "12:46:05", "13:02:20"],
  "elapsed_since_last_winner_minutes": 6,
  "target_hit_probability": 0.75,
  "max_wait_minutes": 30
}'
```

## Publicar en GitHub + usar en skills.sh

1. Crear repo remoto y push:

```bash
gh repo create broomva/alkosto-wait-optimizer-skill --public --source . --remote origin --push
```

2. Instalar skill desde GitHub:

```bash
npx skills add https://github.com/broomva/alkosto-wait-optimizer-skill --skill alkosto-wait-optimizer --yes
```
