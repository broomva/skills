import { fail, ok, type ParallaxError, type Result } from "./errors";

/**
 * Input shapes, described once, in a form with no dependencies.
 *
 * Two adapters need the same shapes and they need them to be the SAME shapes:
 * an MCP/JSON-Schema surface and a Zod surface that disagree by one optional
 * field produce a model that calls the tool correctly on one transport and
 * incorrectly on the other. So the shape is data here, and `toJsonSchema` and
 * `toZod` are projections of it.
 *
 * Three deliberate restrictions, each of which has bitten somebody:
 *
 *   - No unions and no free-form records. Zod-to-JSON-Schema conversions across
 *     an MCP boundary degrade unions and drop nested defaults, and a model that
 *     omits `seed` and receives `undefined` where the code expected 42 produces
 *     a run that is irreproducible for a reason nobody can see.
 *   - Arrays of FLAT objects are the only compound shape.
 *   - Every default is applied twice: once here, once at the top of the handler.
 *     A default that exists in only one of those two places is a default that
 *     disappears on the transport that skipped it.
 */

export type Field =
  | {
      readonly kind: "string";
      readonly description: string;
      readonly optional?: true;
      readonly default?: string;
      readonly enum?: readonly string[];
      readonly minLength?: number;
    }
  | {
      readonly kind: "number";
      readonly description: string;
      readonly optional?: true;
      readonly default?: number;
      readonly int?: true;
      readonly min?: number;
      readonly max?: number;
    }
  | {
      readonly kind: "boolean";
      readonly description: string;
      readonly optional?: true;
      readonly default?: boolean;
    }
  | {
      readonly kind: "strings";
      readonly description: string;
      readonly optional?: true;
    }
  | {
      readonly kind: "objects";
      readonly description: string;
      readonly optional?: true;
      readonly fields: Readonly<Record<string, Field>>;
    };

export interface ObjectSpec {
  readonly fields: Readonly<Record<string, Field>>;
}

export type ValidationError = ParallaxError<"INVALID_INPUT">;

/**
 * Validate and apply defaults, returning a VALUE either way.
 *
 * The tool surface cannot throw on bad input: a thrown validation error becomes
 * prose in a model's context, and prose is not something a caller can branch on.
 * A rejected argument comes back as `{code: "INVALID_INPUT", ...}` with the
 * field named, exactly like every other failure in the system.
 */
export function validate(
  spec: ObjectSpec,
  raw: unknown,
): Result<Record<string, unknown>, ValidationError> {
  if (typeof raw !== "object" || raw === null || Array.isArray(raw)) {
    return fail("INVALID_INPUT", "expected an object of arguments", { received: typeName(raw) });
  }
  const input = raw as Record<string, unknown>;
  const out: Record<string, unknown> = {};

  for (const key of Object.keys(input)) {
    if (!(key in spec.fields)) {
      return fail("INVALID_INPUT", `unknown argument "${key}"`, {
        field: key,
        known: Object.keys(spec.fields),
      });
    }
  }

  for (const [key, field] of Object.entries(spec.fields)) {
    const value = input[key];
    if (value === undefined || value === null) {
      // The default is applied HERE as well as in the handler. Two applications
      // of the same constant is not redundancy: a schema-only default vanishes
      // on any transport that does not run the schema.
      const fallback =
        field.kind === "objects" || field.kind === "strings" ? undefined : field.default;
      if (fallback !== undefined) {
        out[key] = fallback;
        continue;
      }
      if (field.optional !== true) {
        return fail("INVALID_INPUT", `"${key}" is required`, { field: key });
      }
      continue;
    }
    const checked = checkField(key, field, value);
    if (!checked.ok) return checked;
    out[key] = checked.value;
  }
  return ok(out);
}

function hasDefault(field: Field): boolean {
  return field.kind !== "objects" && field.kind !== "strings" && field.default !== undefined;
}

function typeName(v: unknown): string {
  return v === null ? "null" : Array.isArray(v) ? "array" : typeof v;
}

function checkField(key: string, field: Field, value: unknown): Result<unknown, ValidationError> {
  switch (field.kind) {
    case "string": {
      if (typeof value !== "string") {
        return fail("INVALID_INPUT", `"${key}" must be a string`, {
          field: key,
          received: typeName(value),
        });
      }
      if (field.minLength !== undefined && value.length < field.minLength) {
        return fail("INVALID_INPUT", `"${key}" must be at least ${field.minLength} characters`, {
          field: key,
        });
      }
      if (field.enum !== undefined && !field.enum.includes(value)) {
        return fail("INVALID_INPUT", `"${key}" must be one of ${field.enum.join(", ")}`, {
          field: key,
          given: value,
          allowed: field.enum,
        });
      }
      return ok(value);
    }
    case "number": {
      if (typeof value !== "number" || !Number.isFinite(value)) {
        return fail("INVALID_INPUT", `"${key}" must be a finite number`, {
          field: key,
          received: typeName(value),
        });
      }
      if (field.int === true && !Number.isInteger(value)) {
        return fail("INVALID_INPUT", `"${key}" must be a whole number`, {
          field: key,
          given: value,
        });
      }
      if (field.min !== undefined && value < field.min) {
        return fail("INVALID_INPUT", `"${key}" must be at least ${field.min}`, {
          field: key,
          given: value,
        });
      }
      if (field.max !== undefined && value > field.max) {
        return fail("INVALID_INPUT", `"${key}" must be at most ${field.max}`, {
          field: key,
          given: value,
        });
      }
      return ok(value);
    }
    case "boolean": {
      if (typeof value !== "boolean") {
        return fail("INVALID_INPUT", `"${key}" must be true or false`, {
          field: key,
          received: typeName(value),
        });
      }
      return ok(value);
    }
    case "strings": {
      if (!Array.isArray(value) || value.some((v) => typeof v !== "string")) {
        return fail("INVALID_INPUT", `"${key}" must be an array of strings`, {
          field: key,
          received: typeName(value),
        });
      }
      return ok(value as string[]);
    }
    case "objects": {
      if (!Array.isArray(value)) {
        return fail("INVALID_INPUT", `"${key}" must be an array`, {
          field: key,
          received: typeName(value),
        });
      }
      const rows: Array<Record<string, unknown>> = [];
      for (const [i, row] of value.entries()) {
        const checked = validate({ fields: field.fields }, row);
        if (!checked.ok) {
          return fail("INVALID_INPUT", `"${key}[${i}]": ${checked.error.reason}`, {
            field: key,
            index: i,
            ...checked.error.detail,
          });
        }
        rows.push(checked.value);
      }
      return ok(rows);
    }
    default:
      return fail("INVALID_INPUT", `"${key}" has an unsupported shape`, { field: key });
  }
}

// ---------------------------------------------------------------------------
// projections
// ---------------------------------------------------------------------------

export interface JsonSchemaObject {
  type: "object";
  properties: Record<string, unknown>;
  required: string[];
  additionalProperties: false;
}

export function toJsonSchema(spec: ObjectSpec): JsonSchemaObject {
  const properties: Record<string, unknown> = {};
  const required: string[] = [];
  for (const [key, field] of Object.entries(spec.fields)) {
    properties[key] = fieldToJsonSchema(field);
    if (field.optional !== true && !hasDefault(field)) required.push(key);
  }
  return { type: "object", properties, required, additionalProperties: false };
}

function fieldToJsonSchema(field: Field): Record<string, unknown> {
  switch (field.kind) {
    case "string":
      return {
        type: "string",
        description: field.description,
        ...(field.enum === undefined ? {} : { enum: [...field.enum] }),
        ...(field.minLength === undefined ? {} : { minLength: field.minLength }),
        ...(field.default === undefined ? {} : { default: field.default }),
      };
    case "number":
      return {
        type: field.int === true ? "integer" : "number",
        description: field.description,
        ...(field.min === undefined ? {} : { minimum: field.min }),
        ...(field.max === undefined ? {} : { maximum: field.max }),
        ...(field.default === undefined ? {} : { default: field.default }),
      };
    case "boolean":
      return {
        type: "boolean",
        description: field.description,
        ...(field.default === undefined ? {} : { default: field.default }),
      };
    case "strings":
      return { type: "array", description: field.description, items: { type: "string" } };
    case "objects":
      return {
        type: "array",
        description: field.description,
        items: toJsonSchema({ fields: field.fields }),
      };
    default:
      return { description: "unsupported" };
  }
}

/**
 * The minimum of Zod this file uses.
 *
 * Structural, so `zod` is never imported here and never becomes a dependency of
 * the core test suite. A caller that has Zod passes `z` straight in; a caller
 * that does not can still use `toJsonSchema` and get identical validation, since
 * both are projections of the same `ObjectSpec`.
 */
export interface ZodTypeLike {
  optional(): ZodTypeLike;
  default(value: unknown): ZodTypeLike;
  describe(text: string): ZodTypeLike;
}
export interface ZodStringLike extends ZodTypeLike {
  min(n: number): ZodStringLike;
}
export interface ZodNumberLike extends ZodTypeLike {
  int(): ZodNumberLike;
  min(n: number): ZodNumberLike;
  max(n: number): ZodNumberLike;
}
export interface ZodLike {
  object(shape: Record<string, ZodTypeLike>): ZodTypeLike;
  array(item: ZodTypeLike): ZodTypeLike;
  string(): ZodStringLike;
  number(): ZodNumberLike;
  boolean(): ZodTypeLike;
  enum(values: string[]): ZodTypeLike;
}

export function toZod(z: ZodLike, spec: ObjectSpec): ZodTypeLike {
  const shape: Record<string, ZodTypeLike> = {};
  for (const [key, field] of Object.entries(spec.fields)) {
    shape[key] = fieldToZod(z, field);
  }
  return z.object(shape);
}

function fieldToZod(z: ZodLike, field: Field): ZodTypeLike {
  let t: ZodTypeLike;
  switch (field.kind) {
    case "string": {
      let s: ZodStringLike = z.string();
      if (field.minLength !== undefined) s = s.min(field.minLength);
      t = field.enum === undefined ? s : z.enum([...field.enum]);
      break;
    }
    case "number": {
      let n: ZodNumberLike = z.number();
      if (field.int === true) n = n.int();
      if (field.min !== undefined) n = n.min(field.min);
      if (field.max !== undefined) n = n.max(field.max);
      t = n;
      break;
    }
    case "boolean":
      t = z.boolean();
      break;
    case "strings":
      t = z.array(z.string());
      break;
    case "objects":
      t = z.array(toZod(z, { fields: field.fields }));
      break;
    default:
      t = z.string();
      break;
  }
  t = t.describe(field.description);
  if (hasDefault(field) && field.kind !== "objects" && field.kind !== "strings") {
    return t.default(field.default);
  }
  if (field.optional === true) return t.optional();
  return t;
}
