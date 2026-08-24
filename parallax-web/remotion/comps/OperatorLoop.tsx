import { AbsoluteFill, useCurrentFrame } from "remotion";
import { at, C, Caption, ease, Mono, Rail, Stage, Tag } from "../kit";

/**
 * The multi-site operator loop, drawn on the runtime that already exists.
 *
 * observar → estructurar → predecir → simular → recomendar → medir → recalibrar
 *
 * Each station is a Parallax operator, not a new subsystem: structuring is
 * proposeOntology plus the accept gate, simulating is a fork and a rollout,
 * measuring is what turns a simulated quantity into an observed one, and
 * recalibrating is the branch writing its own class back down.
 *
 * The Spanish is deliberate. The recommendation is a WhatsApp message to a
 * Colombian operator, and translating it into English would be showing a
 * message the product would never send.
 */

const STATIONS = [
  "observar",
  "estructurar",
  "predecir",
  "simular",
  "recomendar",
  "medir",
  "recalibrar",
];

const TRACK_Y = 236;
const X_A = 150;
const X_B = 1450;
const sx = (i: number) => X_A + (i / (STATIONS.length - 1)) * (X_B - X_A);

// where each phase starts, in frames
const START = [10, 56, 108, 152, 216, 268, 306];
const DETAIL_Y = 380;

export const OperatorLoop: React.FC = () => {
  const f = useCurrentFrame();

  const phase = START.reduce((acc, s, i) => (f >= s ? i : acc), 0);
  // the token glides between stations rather than jumping
  const next = Math.min(phase + 1, STATIONS.length - 1);
  const span = (START[next] ?? START[phase] + 40) - START[phase];
  const t = span <= 0 ? 1 : ease(f, START[phase], Math.min(span, 22));
  const tokenX = sx(phase) + (sx(next) - sx(phase)) * (phase === next ? 0 : t);

  const on = (i: number) => at(f, START[i], 10) * (1 - at(f, (START[i + 1] ?? 9999) - 6, 8));

  return (
    <AbsoluteFill>
      <Stage>
        <Rail left="OPERADOR MULTI-SEDE" right="cada estación ya existe" />

        {/* ---- the track ---- */}
        <line x1={X_A} y1={TRACK_Y} x2={X_B} y2={TRACK_Y} stroke={C.axis} />
        {/* the loop closes: what was measured re-enters as observation */}
        <path
          d={`M${X_B} ${TRACK_Y} C ${X_B + 70} ${TRACK_Y + 92}, ${X_A - 70} ${TRACK_Y + 92}, ${X_A} ${TRACK_Y}`}
          fill="none"
          stroke={C.accent}
          strokeWidth={2}
          strokeDasharray="2 9"
          opacity={at(f, START[6])}
        />
        <Mono
          x={(X_A + X_B) / 2}
          y={TRACK_Y + 112}
          size={27}
          anchor="middle"
          fill={C.accent}
          opacity={at(f, START[6] + 8)}
        >
          lo medido vuelve a entrar como observación
        </Mono>

        {STATIONS.map((s, i) => {
          const done = f >= START[i];
          return (
            <g key={s}>
              <circle
                cx={sx(i)}
                cy={TRACK_Y}
                r={9}
                fill={done ? C.accent : C.bg}
                stroke={done ? C.accent : C.faint}
                strokeWidth={2.5}
              />
              <Mono
                x={sx(i)}
                y={TRACK_Y - 34}
                size={27}
                anchor="middle"
                fill={i === phase ? C.fg : C.faint}
              >
                {s}
              </Mono>
            </g>
          );
        })}
        <circle
          cx={tokenX}
          cy={TRACK_Y}
          r={16}
          fill="none"
          stroke={C.accent}
          strokeWidth={2}
          opacity={0.7}
        />

        {/* ---- 01 observar ---- */}
        <g opacity={on(0)}>
          <Tag x={150} y={DETAIL_Y} fill={C.faint}>
            LO QUE YA EXISTE, SIN INTEGRARLO PRIMERO
          </Tag>
          {[
            ["POS", "4 sedes · 61 días de ventas"],
            ["WhatsApp", "pedidos, turnos, proveedores"],
            ["hojas y archivos", "inventario, nómina, recetas"],
          ].map(([k, v], i) => (
            <g key={k} opacity={at(f, 16 + i * 10)}>
              <rect
                x={150}
                y={DETAIL_Y + 40 + i * 96}
                width={1180}
                height={72}
                rx={12}
                fill="none"
                stroke={C.rule}
              />
              <Mono x={186} y={DETAIL_Y + 86 + i * 96} size={35} fill={C.fg}>
                {k}
              </Mono>
              <Mono x={1294} y={DETAIL_Y + 86 + i * 96} size={30} anchor="end" fill={C.dim}>
                {v}
              </Mono>
            </g>
          ))}
        </g>

        {/* ---- 02 estructurar ---- */}
        <g opacity={on(1)}>
          <Tag x={150} y={DETAIL_Y} fill={C.faint}>
            proposeOntology → LA PROPUESTA, ANTES DE QUE CORRA NADA
          </Tag>
          {[
            ["sedes", "4"],
            ["empleados", "37"],
            ["inventario", "212 SKU"],
            ["turnos", "por sede · por franja"],
            ["proveedores", "9"],
            ["invariante", "insumo consumido ≤ insumo disponible"],
          ].map(([k, v], i) => (
            <g key={k} opacity={at(f, 62 + i * 6)}>
              <Mono
                x={150 + (i % 2) * 620}
                y={DETAIL_Y + 60 + Math.floor(i / 2) * 62}
                size={30}
                fill={C.tag}
              >
                {k}
              </Mono>
              <Mono
                x={150 + (i % 2) * 620 + 560}
                y={DETAIL_Y + 60 + Math.floor(i / 2) * 62}
                size={30}
                anchor="end"
                fill={C.fg}
              >
                {v}
              </Mono>
            </g>
          ))}
          <Mono x={150} y={DETAIL_Y + 268} size={30} fill={C.accent} opacity={at(f, 92)}>
            aceptada por el operador · sin aceptación no hay pronóstico
          </Mono>
        </g>

        {/* ---- 03 predecir ---- */}
        <g opacity={on(2)}>
          <Tag x={150} y={DETAIL_Y} fill={C.faint}>
            PRONÓSTICO SOBRE ENTIDADES REALES, NO SOBRE UNA SERIE ANÓNIMA
          </Tag>
          <Mono x={150} y={DETAIL_Y + 82} size={43} fill={C.fg}>
            Chapinero · viernes · +22% en ventas
          </Mono>
          <rect
            x={150}
            y={DETAIL_Y + 120}
            width={1180}
            height={18}
            rx={9}
            fill={C.grid}
            stroke={C.rule}
          />
          <rect
            x={150}
            y={DETAIL_Y + 120}
            width={1180 * 0.72 * ease(f, 118, 24)}
            height={18}
            rx={9}
            fill={C.accent}
          />
          <Mono x={150} y={DETAIL_Y + 190} size={30} fill={C.accent}>
            simulado — todavía no ha pasado nada
          </Mono>
        </g>

        {/* ---- 04 simular ---- */}
        <g opacity={on(3)}>
          <Tag x={150} y={DETAIL_Y} fill={C.faint}>
            rollout → diff · DOS RAMAS DESDE EL MISMO ESTADO
          </Tag>
          <rect
            x={150}
            y={DETAIL_Y + 40}
            width={570}
            height={230}
            rx={12}
            fill="none"
            stroke={C.rule}
          />
          <Mono x={186} y={DETAIL_Y + 92} size={35} fill={C.fg}>
            no hacer nada
          </Mono>
          <Mono x={186} y={DETAIL_Y + 142} size={30} fill={C.crit}>
            faltan 2 insumos
          </Mono>
          <Mono x={186} y={DETAIL_Y + 186} size={30} fill={C.crit}>
            déficit de personal 7–9 p.m.
          </Mono>
          <rect
            x={760}
            y={DETAIL_Y + 40}
            width={570}
            height={230}
            rx={12}
            fill={C.accentSoft}
            stroke={C.accent}
          />
          <Mono x={796} y={DETAIL_Y + 92} size={35} fill={C.fg}>
            mover a Cindy · +18 kg
          </Mono>
          <Mono x={796} y={DETAIL_Y + 142} size={30} fill={C.ok}>
            0 faltantes
          </Mono>
          <Mono x={796} y={DETAIL_Y + 186} size={30} fill={C.ok}>
            turno cubierto
          </Mono>
        </g>

        {/* ---- 05 recomendar ---- */}
        <g opacity={on(4)}>
          <Tag x={150} y={DETAIL_Y} fill={C.faint}>
            AL CANAL DONDE LA EMPRESA YA TRABAJA
          </Tag>
          <rect
            x={150}
            y={DETAIL_Y + 40}
            width={1180}
            height={252}
            rx={14}
            fill="none"
            stroke={C.accent}
          />
          <Mono x={186} y={DETAIL_Y + 92} size={30} fill={C.dim}>
            La sede de Chapinero venderá ~22% más este viernes.
          </Mono>
          <Mono x={186} y={DETAIL_Y + 138} size={30} fill={C.dim}>
            Si no haces nada faltarán dos insumos y habrá déficit 7–9 p.m.
          </Mono>
          <Mono x={186} y={DETAIL_Y + 184} size={30} fill={C.fg}>
            Recomiendo mover a Cindy y ordenar 18 kg adicionales.
          </Mono>
          <Mono x={186} y={DETAIL_Y + 236} size={35} fill={C.accent}>
            ¿Lo ejecuto?
          </Mono>
          <Mono x={1294} y={DETAIL_Y + 236} size={27} anchor="end" fill={C.faint}>
            recibo: /r/bef312a9
          </Mono>
        </g>

        {/* ---- 06 medir ---- */}
        <g opacity={on(5)}>
          <Tag x={150} y={DETAIL_Y} fill={C.faint}>
            LO QUE PASÓ DE VERDAD
          </Tag>
          <Mono x={150} y={DETAIL_Y + 88} size={43} fill={C.fg}>
            +19% real · 0 faltantes · turno cubierto
          </Mono>
          <rect x={150} y={DETAIL_Y + 128} width={18} height={18} rx={5} fill={C.ok} />
          <Mono x={182} y={DETAIL_Y + 144} size={30} fill={C.ok}>
            observado — la cantidad cambia de tipo, no de nombre
          </Mono>
        </g>

        {/* ---- 07 recalibrar ---- */}
        <g opacity={at(f, START[6], 10)}>
          <Tag x={150} y={DETAIL_Y} fill={C.faint}>
            EL HISTORIAL CALIBRADO ES LO QUE NO SE PUEDE COPIAR
          </Tag>
          <Mono x={150} y={DETAIL_Y + 88} size={35} fill={C.fg}>
            pronóstico +22% → real +19% · error 3 puntos
          </Mono>
          <Mono x={150} y={DETAIL_Y + 140} size={30} fill={C.dim}>
            predicción → decisión → resultado, una fila más en el registro
          </Mono>
        </g>

        <Caption from={START[6] + 16}>
          Cada estación es un operador que ya corre. El bucle es el producto.
        </Caption>
      </Stage>
    </AbsoluteFill>
  );
};

export const OPERATOR_LOOP_DURATION = 380;
